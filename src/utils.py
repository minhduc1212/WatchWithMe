import os
import re
import subprocess
import json
from src.config import MEDIA_DIR, logger
from src.database import get_db

def srt_to_vtt(srt_content: str) -> str:
    """
    Convert SRT subtitle format to WebVTT.
    """
    lines = srt_content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    vtt_lines = ["WEBVTT", ""]
    for line in lines:
        if "-->" in line:
            line = line.replace(',', '.')
        vtt_lines.append(line)
    return '\n'.join(vtt_lines)

def get_video_duration(input_path: str) -> int:
    """
    Get video duration in seconds using ffprobe.
    """
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", input_path
    ]
    logger.info(f"Running FFprobe to extract duration: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        duration = int(float(result.stdout.strip()))
        logger.info(f"Extracted video duration: {duration}s")
        return duration
    except Exception as e:
        logger.error(f"Error getting video duration: {e}")
        return 0

def get_video_info(file_path: str) -> dict:
    """
    Run ffprobe to analyze video, audio, and subtitle streams.
    """
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "stream=index,codec_type,codec_name:stream_tags=language,title",
        "-of", "json", file_path
    ]
    logger.info(f"Probing media file: {file_path}")
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        info = json.loads(result.stdout)
        
        streams = info.get("streams", [])
        video_streams = []
        audio_streams = []
        subtitle_streams = []
        
        for s in streams:
            codec_type = s.get("codec_type")
            index = s.get("index")
            codec_name = s.get("codec_name")
            tags = s.get("tags", {}) or {}
            lang = tags.get("language", "und")
            title = tags.get("title", f"Track {index}")
            
            stream_info = {
                "index": index,
                "codec": codec_name,
                "language": lang,
                "title": title
            }
            
            if codec_type == "video":
                video_streams.append(stream_info)
            elif codec_type == "audio":
                audio_streams.append(stream_info)
            elif codec_type == "subtitle":
                # Filter text-based subtitles only, graphics-based like pgs/dvd_sub won't easily convert to vtt
                text_codecs = ["subrip", "srt", "ass", "ssa", "webvtt", "mov_text"]
                if codec_name in text_codecs:
                    subtitle_streams.append(stream_info)
                else:
                    logger.info(f"Skipping non-text subtitle track {index} of codec type '{codec_name}'")
                    
        return {
            "video": video_streams,
            "audio": audio_streams,
            "subtitle": subtitle_streams
        }
    except Exception as e:
        logger.error(f"Error probing file {file_path}: {e}")
        return {"video": [], "audio": [], "subtitle": []}

def extract_subtitle(file_path: str, stream_index: int, output_vtt_path: str) -> bool:
    """
    Extract a subtitle stream and save it as WebVTT.
    """
    cmd = [
        "ffmpeg", "-y", "-i", file_path,
        "-map", f"0:{stream_index}",
        output_vtt_path
    ]
    try:
        logger.info(f"Extracting subtitle stream {stream_index} to {output_vtt_path}...")
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return True
    except Exception as e:
        logger.error(f"Failed to extract subtitle stream {stream_index}: {e}")
        return False

def parse_ffmpeg_progress(line: str, duration: int) -> int:
    """
    Parse the progress time out of FFmpeg output lines and return progress percentage.
    """
    if duration <= 0:
        return 0
    # Look for time=HH:MM:SS.xx
    match = re.search(r"time=(\d+):(\d+):(\d+)\.(\d+)", line)
    if match:
        hours, minutes, seconds, _ = map(int, match.groups())
        current_time = hours * 3600 + minutes * 60 + seconds
        progress = int((current_time / duration) * 100)
        return min(100, max(0, progress))
    return None

def process_video_task(movie_id: int, temp_file_path: str, audio_track_index: int = None, subtitle_track_indexes: list = None):
    """
    Transcode video to HLS, extract selected subtitles, and generate thumbnail.
    """
    logger.info(f"[Process-{movie_id}] Starting video transcoding task for movie_id: {movie_id}")
    
    movie_media_dir = os.path.join(MEDIA_DIR, "videos", str(movie_id))
    os.makedirs(movie_media_dir, exist_ok=True)
    
    playlist_path = os.path.join(movie_media_dir, "index.m3u8")
    thumbnail_path = os.path.join(MEDIA_DIR, "thumbnails", f"{movie_id}.jpg")
    
    conn = get_db()
    
    try:
        # 1. Probing video duration
        duration = get_video_duration(temp_file_path)
        
        # 2. Extracting thumbnail
        thumb_time = "00:00:02" if duration > 5 else "00:00:00"
        thumb_cmd = [
            "ffmpeg", "-y", "-i", temp_file_path,
            "-ss", thumb_time, "-vframes", "1",
            "-vf", "scale=640:-1",
            thumbnail_path
        ]
        logger.info(f"[Process-{movie_id}] Extracting thumbnail: {' '.join(thumb_cmd)}")
        thumb_result = subprocess.run(thumb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if thumb_result.returncode != 0:
            logger.warning(f"[Process-{movie_id}] Thumbnail extraction warning: {thumb_result.stderr}")
        else:
            logger.info(f"[Process-{movie_id}] Thumbnail successfully extracted.")
            
        # 3. Extract subtitles if selected
        if subtitle_track_indexes and isinstance(subtitle_track_indexes, list):
            import uuid
            # Get video info to find original titles/languages
            video_info = get_video_info(temp_file_path)
            sub_tracks_map = {track["index"]: track for track in video_info.get("subtitle", [])}
            
            for idx in subtitle_track_indexes:
                try:
                    track_info = sub_tracks_map.get(int(idx))
                    lang = "English"
                    if track_info:
                        lang = track_info.get("title") or track_info.get("language") or "Unknown"
                        
                    subtitle_filename = f"{movie_id}_{uuid.uuid4().hex[:8]}.vtt"
                    subtitle_path = os.path.join(MEDIA_DIR, "subtitles", subtitle_filename)
                    
                    if extract_subtitle(temp_file_path, int(idx), subtitle_path):
                        vtt_url = f"/media/subtitles/{subtitle_filename}"
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO subtitles (movie_id, language, vtt_url) VALUES (?, ?, ?)",
                            (movie_id, lang, vtt_url)
                        )
                        conn.commit()
                        logger.info(f"[Process-{movie_id}] Extracted internal subtitle track {idx} ({lang}) to {vtt_url}")
                except Exception as ex:
                    logger.error(f"[Process-{movie_id}] Failed to extract subtitle track {idx}: {ex}")

        # 4. Packaging to HLS stream with progress tracking
        # Construct HLS command mapping specific audio track if chosen
        hls_cmd = [
            "ffmpeg", "-y", "-i", temp_file_path,
            "-map", "0:v:0"
        ]
        
        if audio_track_index is not None:
            hls_cmd.extend(["-map", f"0:{audio_track_index}"])
        else:
            hls_cmd.extend(["-map", "0:a:0?"])
            
        hls_cmd.extend([
            "-sn",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-start_number", "0",
            "-hls_time", "5",
            "-hls_list_size", "0",
            "-hls_flags", "single_file",
            "-f", "hls",
            playlist_path
        ])
        
        logger.info(f"[Process-{movie_id}] Launching FFmpeg transcode: {' '.join(hls_cmd)}")
        
        process = subprocess.Popen(
            hls_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        last_progress = 0
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                # Parse progress percentage
                progress = parse_ffmpeg_progress(clean_line, duration)
                if progress is not None and progress != last_progress:
                    last_progress = progress
                    cursor = conn.cursor()
                    cursor.execute("UPDATE movies SET progress = ? WHERE id = ?", (progress, movie_id))
                    conn.commit()
                    logger.info(f"[Process-{movie_id}] Packaging progress: {progress}%")
                    
        process.wait()
        if process.returncode != 0:
            raise Exception(f"FFmpeg HLS transcode failed with exit code {process.returncode}")
            
        logger.info(f"[Process-{movie_id}] Transcoding successfully completed.")
        
        playlist_url = f"/media/videos/{movie_id}/index.m3u8"
        thumbnail_url = f"/media/thumbnails/{movie_id}.jpg"
        
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE movies SET duration = ?, playlist_url = ?, thumbnail_url = ?, status = 'ready', progress = 100 WHERE id = ?",
            (duration, playlist_url, thumbnail_url, movie_id)
        )
        conn.commit()
        logger.info(f"[Process-{movie_id}] Movie status updated to READY.")
        
    except Exception as e:
        logger.error(f"[Process-{movie_id}] Transcoding error: {e}")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE movies SET status = 'failed', error_message = ? WHERE id = ?",
            (str(e), movie_id)
        )
        conn.commit()
    finally:
        conn.close()
        # Clean up temp file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"[Process-{movie_id}] Cleaned up temp file: {temp_file_path}")
            except Exception as ex:
                logger.warning(f"[Process-{movie_id}] Could not remove temp file: {ex}")
