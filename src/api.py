import os
import shutil
import uuid
import mimetypes
from typing import List
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from src.config import TEMP_DIR, MEDIA_DIR, logger
from src.database import get_db
from src.utils import get_video_info, process_video_task, srt_to_vtt
from src.tunnel import get_tunnel_url


router = APIRouter()


def send_bytes_range_requests(file_path: str, start: int, end: int, chunk_size: int = 1024 * 64):
    with open(file_path, mode="rb") as f:
        f.seek(start)
        pos = start
        while pos <= end:
            read_size = min(chunk_size, end - pos + 1)
            data = f.read(read_size)
            if not data:
                break
            pos += len(data)
            yield data


@router.get("/media/{file_path:path}")
def serve_media(file_path: str, request: Request):
    path = os.path.join(MEDIA_DIR, file_path)
    if not os.path.exists(path) or os.path.isdir(path):
        raise HTTPException(status_code=404, detail="File not found")

    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = "application/octet-stream"

    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(path, media_type=mime_type)

    try:
        range_str = range_header.replace("bytes=", "").strip()
        parts = range_str.split("-")
        if not parts[0]:
            start = file_size - int(parts[1])
            end = file_size - 1
        else:
            start = int(parts[0])
            end = int(parts[1]) if parts[1] else file_size - 1
        
        if start >= file_size or end >= file_size or start > end:
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=416, detail="Requested Range Not Satisfiable")

    content_length = end - start + 1
    
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Access-Control-Allow-Origin": "*",
    }

    return StreamingResponse(
        send_bytes_range_requests(path, start, end),
        status_code=206,
        media_type=mime_type,
        headers=headers
    )




@router.get("/api/movies")
def list_movies(q: str = None):
    logger.info(f"API List Movies requested. Search query q='{q}'")
    conn = get_db()
    cursor = conn.cursor()
    if q:
        cursor.execute(
            "SELECT * FROM movies WHERE (title LIKE ? OR description LIKE ?) AND status != 'pending_selection' ORDER BY created_at DESC",
            (f"%{q}%", f"%{q}%")
        )
    else:
        cursor.execute("SELECT * FROM movies WHERE status != 'pending_selection' ORDER BY created_at DESC")
    
    movies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return movies

@router.get("/api/movies/{movie_id}")
def get_movie(movie_id: int):
    logger.info(f"API Get Movie requested for movie_id: {movie_id}")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
    movie = cursor.fetchone()
    if not movie:
        conn.close()
        raise HTTPException(status_code=404, detail="Movie not found")
        
    cursor.execute("SELECT * FROM subtitles WHERE movie_id = ?", (movie_id,))
    subtitles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    movie_dict = dict(movie)
    movie_dict["subtitles"] = subtitles
    return movie_dict

@router.post("/api/movies/upload")
async def upload_movie(
    title: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    subtitle_file: UploadFile = File(None),
    subtitle_lang: str = Form("English")
):
    logger.info(f"API Upload Movie requested. Title: '{title}', Filename: '{file.filename}'")
    temp_id = str(uuid.uuid4())
    temp_file_name = f"{temp_id}_{file.filename}"
    temp_file_path = os.path.join(TEMP_DIR, temp_file_name)
    
    # Save the file to temp location
    try:
        logger.info(f"Saving uploaded file stream to temp directory: {temp_file_path}")
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info("Upload file successfully stored in temp space.")
    except Exception as e:
        logger.error(f"Failed to write uploaded file to temp: {e}")
        raise HTTPException(status_code=500, detail=f"Could not save uploaded file: {e}")
        
    # Probe file to list streams
    video_info = get_video_info(temp_file_path)
    
    # Insert initial movie metadata in database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO movies (title, description, status, playlist_url) VALUES (?, ?, 'pending_selection', ?)",
        (title, description, temp_file_name) # Temporarily store temp file name here
    )
    movie_id = cursor.lastrowid
    conn.commit()
    
    # Process custom subtitles if uploaded
    if subtitle_file:
        try:
            logger.info(f"Processing subtitle file during upload: '{subtitle_file.filename}'")
            content_bytes = await subtitle_file.read()
            content_str = content_bytes.decode("utf-8", errors="ignore")
            
            if subtitle_file.filename.endswith(".srt"):
                vtt_content = srt_to_vtt(content_str)
            else:
                vtt_content = content_str
                
            subtitle_filename = f"{movie_id}_{uuid.uuid4().hex[:8]}.vtt"
            subtitle_path = os.path.join(MEDIA_DIR, "subtitles", subtitle_filename)
            
            with open(subtitle_path, "w", encoding="utf-8") as f:
                f.write(vtt_content)
                
            vtt_url = f"/media/subtitles/{subtitle_filename}"
            cursor.execute(
                "INSERT INTO subtitles (movie_id, language, vtt_url) VALUES (?, ?, ?)",
                (movie_id, subtitle_lang, vtt_url)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving custom subtitle: {e}")
            
    conn.close()
    
    return {
        "movie_id": movie_id,
        "status": "pending_selection",
        "audio_tracks": video_info["audio"],
        "subtitle_tracks": video_info["subtitle"]
    }

@router.post("/api/movies/{movie_id}/process")
def process_movie(
    movie_id: int,
    background_tasks: BackgroundTasks,
    audio_track_index: int = Form(None),
    subtitle_track_indexes: str = Form(None) # Comma-separated list of track indices
):
    """
    Enqueues the HLS stream packaging background task with selected audio/subtitle options.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT playlist_url, status FROM movies WHERE id = ?", (movie_id,))
    movie = cursor.fetchone()
    if not movie:
        conn.close()
        raise HTTPException(status_code=404, detail="Movie not found")
        
    if movie["status"] != "pending_selection":
        conn.close()
        raise HTTPException(status_code=400, detail="Movie has already started or completed packaging")
        
    temp_file_name = movie["playlist_url"]
    temp_file_path = os.path.join(TEMP_DIR, temp_file_name)
    
    if not os.path.exists(temp_file_path):
        conn.close()
        raise HTTPException(status_code=404, detail="Uploaded file missing in temp directory")
        
    # Update status to processing
    cursor.execute("UPDATE movies SET status = 'processing', progress = 0 WHERE id = ?", (movie_id,))
    conn.commit()
    conn.close()
    
    # Parse subtitle indices
    sub_indexes = []
    if subtitle_track_indexes:
        sub_indexes = [int(idx.strip()) for idx in subtitle_track_indexes.split(",") if idx.strip().isdigit()]
        
    logger.info(f"Enqueuing process task for movie_id {movie_id} with audio_track={audio_track_index}, subtitles={sub_indexes}")
    
    background_tasks.add_task(
        process_video_task,
        movie_id,
        temp_file_path,
        audio_track_index,
        sub_indexes
    )
    
    return {"message": "Packaging started", "movie_id": movie_id}

@router.post("/api/movies/{movie_id}/subtitles")
async def add_subtitle(
    movie_id: int,
    language: str = Form(...),
    file: UploadFile = File(...)
):
    logger.info(f"API Add Subtitle requested for movie_id: {movie_id}, Language: {language}")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM movies WHERE id = ?", (movie_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Movie not found")
        
    try:
        content_bytes = await file.read()
        content_str = content_bytes.decode("utf-8", errors="ignore")
        
        if file.filename.endswith(".srt"):
            vtt_content = srt_to_vtt(content_str)
        else:
            vtt_content = content_str
            
        subtitle_filename = f"{movie_id}_{uuid.uuid4().hex[:8]}.vtt"
        subtitle_path = os.path.join(MEDIA_DIR, "subtitles", subtitle_filename)
        
        with open(subtitle_path, "w", encoding="utf-8") as f:
            f.write(vtt_content)
            
        vtt_url = f"/media/subtitles/{subtitle_filename}"
        cursor.execute(
            "INSERT INTO subtitles (movie_id, language, vtt_url) VALUES (?, ?, ?)",
            (movie_id, language, vtt_url)
        )
        conn.commit()
    except Exception as e:
        conn.close()
        logger.error(f"Error saving subtitle track: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving subtitle: {e}")
        
    conn.close()
    return {"message": "Subtitle added successfully", "vtt_url": vtt_url}

@router.delete("/api/movies/{movie_id}")
def delete_movie(movie_id: int):
    logger.info(f"API Delete Movie requested for movie_id: {movie_id}")
    conn = get_db()
    cursor = conn.cursor()
    
    # Get movie details to delete files
    cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
    movie = cursor.fetchone()
    if not movie:
        conn.close()
        raise HTTPException(status_code=404, detail="Movie not found")
        
    # Delete movie files
    movie_media_dir = os.path.join(MEDIA_DIR, "videos", str(movie_id))
    if os.path.exists(movie_media_dir):
        shutil.rmtree(movie_media_dir)
        
    thumbnail_path = os.path.join(MEDIA_DIR, "thumbnails", f"{movie_id}.jpg")
    if os.path.exists(thumbnail_path):
        os.remove(thumbnail_path)
        
    # Delete subtitles associated
    cursor.execute("SELECT vtt_url FROM subtitles WHERE movie_id = ?", (movie_id,))
    subtitles = cursor.fetchall()
    for sub in subtitles:
        sub_rel_path = sub["vtt_url"].lstrip("/")
        # Remove media prefix and replace with MEDIA_DIR path
        if sub_rel_path.startswith("media/"):
            sub_disk_path = sub_rel_path.replace("media", MEDIA_DIR, 1)
            if os.path.exists(sub_disk_path):
                os.remove(sub_disk_path)
                
    # Delete database entries
    cursor.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
    cursor.execute("DELETE FROM subtitles WHERE movie_id = ?", (movie_id,))
    conn.commit()
    conn.close()
    
    logger.info(f"Movie ID {movie_id} and all related disk files deleted successfully.")
    return {"message": "Movie deleted successfully"}

@router.get("/api/tunnel")
def get_tunnel_endpoint():
    return {"url": get_tunnel_url()}

