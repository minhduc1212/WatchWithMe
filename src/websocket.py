import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("WatchWithMe.WebSocket")

class ConnectionManager:
    def __init__(self):
        # room_id -> set of active WebSockets
        self.rooms: Dict[str, Set[WebSocket]] = {}
        # room_id -> room state (current movie, playback state, etc.)
        self.room_states: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
            self.room_states[room_id] = {
                "movie_id": None,
                "time": 0,
                "paused": True
            }
            logger.info(f"Created new room in memory: {room_id}")
        self.rooms[room_id].add(websocket)
        logger.info(f"Client connected to room {room_id}. Active users: {len(self.rooms[room_id])}")
        
        # Send initial room state
        await websocket.send_json({
            "type": "room_state",
            "state": self.room_states[room_id]
        })

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.rooms:
            self.rooms[room_id].discard(websocket)
            logger.info(f"Client disconnected from room {room_id}. Active users left: {len(self.rooms[room_id])}")
            if not self.rooms[room_id]:
                logger.info(f"Room {room_id} is empty. Cleaning up memory.")
                del self.rooms[room_id]
                if room_id in self.room_states:
                    del self.room_states[room_id]

    async def broadcast(self, message: dict, room_id: str, sender: WebSocket = None):
        if room_id in self.rooms:
            logger.info(f"Broadcasting message of type '{message.get('type')}' to room {room_id}")
            for connection in self.rooms[room_id]:
                if connection != sender:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        logger.error(f"Error broadcasting to client in room {room_id}: {e}")

    def update_state(self, room_id: str, state_update: dict):
        if room_id in self.room_states:
            self.room_states[room_id].update(state_update)
            logger.info(f"Updated room {room_id} state in memory to: {self.room_states[room_id]}")

manager = ConnectionManager()
