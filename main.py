import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api import chat, message, file, websocket
from config import UPLOAD_DIR
from database import models
from database.db import engine, Base


@asynccontextmanager
async def lifespan(app):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


chat_app = FastAPI(title='Chat microservice', lifespan=lifespan)

chat_app.include_router(chat.router)
chat_app.include_router(message.router)
chat_app.include_router(file.router)
chat_app.include_router(websocket.router)


@chat_app.get('/health')
async def health():
    return {'status': 'ok'}
