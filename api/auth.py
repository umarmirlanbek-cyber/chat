from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from sqlalchemy import select

from config import SECRET_KEY, ALGORITHM, JWT_USER_CLAIM
from database.models import ChatMember

# tokenUrl нужен только для кнопки Authorize в Swagger
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/login')


def get_user_id_from_token(token):
    """Достаёт id пользователя из токена. Если токен плохой или просрочен, вернёт None."""
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(data[JWT_USER_CLAIM])
    except Exception:
        return None


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Для обычных запросов: берёт токен из заголовка Authorization и возвращает id пользователя."""
    user_id = get_user_id_from_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail='Токен неверный или просрочен')
    return user_id


async def get_member(db, chat_id, user_id):
    """Находит человека среди участников чата. Если его там нет, будет ошибка 403."""
    result = await db.execute(
        select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
    )
    member = result.scalars().first()
    if member is None:
        raise HTTPException(status_code=403, detail='Вы не участник этого чата')
    return member


async def get_member_ids(db, chat_id):
    """Список id всех участников чата."""
    result = await db.execute(select(ChatMember.user_id).where(ChatMember.chat_id == chat_id))
    return result.scalars().all()
