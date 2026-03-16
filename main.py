"""
NFC Relay Server per Railway
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NFC-Relay")

app = FastAPI(title="NFC Relay Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self.card_data: Optional[dict] = None
        self.logs: list = []
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.connections[client_id] = websocket
        logger.info(f"Client connesso: {client_id} (totale: {len(self.connections)})")
        self.log_event("CONNECT", client_id)
    
    def disconnect(self, client_id: str):
        if client_id in self.connections:
            del self.connections[client_id]
        logger.info(f"Client disconnesso: {client_id}")
        self.log_event("DISCONNECT", client_id)
    
    async def broadcast(self, message: str, exclude: str = None):
        for client_id, ws in list(self.connections.items()):
            if client_id != exclude:
                try:
                    await ws.send_text(message)
                except:
                    pass
    
    def log_event(self, event_type: str, client_id: str, data: str = ""):
        self.logs.append({
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "client_id": client_id,
            "data": data[:200] if data else ""
        })
        if len(self.logs) > 500:
            self.logs = self.logs[-500:]

manager = ConnectionManager()

# ============== LICENSE API ==============

@app.get("/api/check_device.php")
async def check_device(device_id: str = Query(...)):
    logger.info(f"Verifica licenza: {device_id}")
    return JSONResponse(content={
        "status": "SUCCESS",
        "message": "Device autorizzato",
        "expires_at": "2099-12-31 23:59:59",
        "device_id": device_id,
        "licensed": True
    })

@app.get("/api/check_device")
async def check_device_alt(device_id: str = Query(...)):
    return await check_device(device_id)

# ============== WEBSOCKET ==============

@app.websocket("/")
async def websocket_main(websocket: WebSocket):
    client_id = f"client_{id(websocket)}"
    try:
        await manager.connect(websocket, client_id)
        while True:
            data = await websocket.receive_text()
            logger.info(f"MSG da {client_id}: {data[:80]}...")
            await manager.broadcast(data, exclude=client_id)
            if len(data) > 50:
                manager.card_data = {"raw": data[:500], "time": datetime.now().isoformat()}
                manager.log_event("DATA", client_id, data)
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"Errore: {e}")
        manager.disconnect(client_id)

@app.websocket("/ws")
async def websocket_ws(websocket: WebSocket):
    await websocket_main(websocket)

# ============== API ==============

@app.get("/")
async def root():
    return {
        "status": "online",
        "server": "NFC Relay",
        "connections": len(manager.connections),
        "clients": list(manager.connections.keys())
    }

@app.get("/api/status")
async def status():
    return {
        "online": True,
        "connections": len(manager.connections),
        "clients": list(manager.connections.keys()),
        "last_card": manager.card_data,
        "logs_count": len(manager.logs)
    }

@app.get("/api/logs")
async def logs(limit: int = 50):
    return {"logs": manager.logs[-limit:]}

# ============== MAIN ==============

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7068))
    print(f"Server avviato su porta {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
