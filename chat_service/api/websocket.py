import asyncio
from fastapi import APIRouter, WebSocket
from chat_service.api.authentication import get_current_user
from chat_service.api.authorization import get_chat_member_ids
from chat_service.database.db import SessionLocal

router = APIRouter(tags=['WebSocket'])

online_users = {}


def remove_socket(user_id, socket):
    sockets = online_users.get(user_id, [])
    if socket in sockets:
        sockets.remove(socket)
    if not sockets:
        online_users.pop(user_id, None)


async def send_to_user(user_id, event):
    for socket in list(online_users.get(user_id, [])):
        try:
            await asyncio.wait_for(socket.send_json(event), timeout=5)
        except Exception:
            remove_socket(user_id, socket)


async def send_to_users(user_ids, event):
    await asyncio.gather(*[send_to_user(user_id, event) for user_id in user_ids])


async def send_typing(user_id, chat_id):
    if not isinstance(chat_id, int):
        return
    async with SessionLocal() as db:
        member_ids = await get_chat_member_ids(db, chat_id)  # получаем участников чата
    if user_id not in member_ids:
        return
    others = [member_id for member_id in member_ids if member_id != user_id]
    await send_to_users(others, {'type': 'typing', 'chat_id': chat_id, 'user_id': user_id})


@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        user = await get_current_user(token)  # проверяем токен через Django
        user_id = user['id']
    except Exception:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    online_users.setdefault(user_id, []).append(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get('type') == 'typing':
                await send_typing(user_id, data.get('chat_id'))
    except Exception:
        pass
    finally:
        remove_socket(user_id, websocket)