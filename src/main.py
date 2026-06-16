import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from src.database import init_db
from src.websocket import manager
from src.api import router as api_router
from src.tunnel import start_tunnel, stop_tunnel

logger = logging.getLogger("WatchWithMe.Main")

# Initialize SQLite database and perform migrations
init_db()

@asynccontextmanager
async def lifespan(app: FastAPI):
    port = int(os.environ.get("PORT", 8000))
    start_tunnel(port=port)
    yield
    stop_tunnel()

# Initialize FastAPI App
app = FastAPI(title="WatchWithMe", lifespan=lifespan)

# Allow CORS for dev ease
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API endpoints (Movie operations, subtitle management, media range server)
app.include_router(api_router)

# WebSocket Endpoint for Watch-Together synchronization
@app.websocket("/ws/room/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            logger.info(f"WS Room {room_id}: Received message of type '{msg_type}'")
            
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                
            elif msg_type == "change_movie":
                movie_id = data.get("movie_id")
                logger.info(f"WS Room {room_id}: Active movie changed to {movie_id}")
                manager.update_state(room_id, {"movie_id": movie_id, "time": 0, "paused": True})
                await manager.broadcast({
                    "type": "change_movie",
                    "movie_id": movie_id
                }, room_id)
                
            elif msg_type == "play":
                time_pos = data.get("time", 0)
                logger.info(f"WS Room {room_id}: Play command received at time {time_pos}s")
                manager.update_state(room_id, {"paused": False, "time": time_pos})
                await manager.broadcast({
                    "type": "play",
                    "time": time_pos
                }, room_id, sender=websocket)
                
            elif msg_type == "pause":
                time_pos = data.get("time", 0)
                logger.info(f"WS Room {room_id}: Pause command received at time {time_pos}s")
                manager.update_state(room_id, {"paused": True, "time": time_pos})
                await manager.broadcast({
                    "type": "pause",
                    "time": time_pos
                }, room_id, sender=websocket)
                
            elif msg_type == "seek":
                time_pos = data.get("time", 0)
                logger.info(f"WS Room {room_id}: Seek command received to {time_pos}s")
                manager.update_state(room_id, {"time": time_pos})
                await manager.broadcast({
                    "type": "seek",
                    "time": time_pos
                }, room_id, sender=websocket)
                
            elif msg_type == "chat":
                nickname = data.get("nickname", "Anonymous")
                message = data.get("message", "")
                logger.info(f"WS Room {room_id}: Chat message from '{nickname}': '{message}'")
                await manager.broadcast({
                    "type": "chat",
                    "nickname": nickname,
                    "message": message
                }, room_id)
                
            elif msg_type == "sync_request":
                state = manager.room_states.get(room_id, {})
                logger.info(f"WS Room {room_id}: Sync state requested. Sending: {state}")
                await websocket.send_json({
                    "type": "room_state",
                    "state": state
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        logger.info(f"WS Room {room_id}: Client disconnected.")
        await manager.broadcast({
            "type": "chat",
            "nickname": "System",
            "message": "A viewer has disconnected."
        }, room_id)
        
    except Exception as e:
        logger.error(f"WS Room {room_id} error occurred: {e}")
        manager.disconnect(websocket, room_id)

# Serve Web UI files
app.mount("/static", StaticFiles(directory="static"), name="static")



@app.get("/")
def read_root():
    return FileResponse("static/index.html")
