from fastapi import HTTPException
from sqlalchemy import select
from chat_service.database.models import ChatMember


async def get_chat_member(db, chat_id: int, user_id: int):
    # Проверяем участника чата
    result = await db.execute(select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id))
    member = result.scalars().first()
    if member is None:
        raise HTTPException(status_code=403, detail='You are not a member of this chat')
    return member


async def get_chat_member_ids(db, chat_id: int):
    # Получаем id участников чата
    result = await db.execute(select(ChatMember.user_id).where(ChatMember.chat_id == chat_id))
    return result.scalars().all()


def require_role(user: dict, *allowed_roles: str):
    # Проверяем роль пользователя
    if user['role'] not in allowed_roles:
        raise HTTPException(status_code=403, detail='You do not have permission')
    return user