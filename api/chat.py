from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func

from api.auth import get_current_user, get_member, get_member_ids
from api.websocket import send_to_users
from database.db import get_db
from database.models import Chat, ChatMember, Message
from database.schema import (
    CreatePrivateChatRequest,
    CreateGroupRequest,
    RenameGroupRequest,
    AddMemberRequest,
    ChatResponse,
    ChatListItemResponse,
    MemberResponse,
)

router = APIRouter(prefix='/chats', tags=['Chats'])

MAX_GROUP_SIZE = 256


async def get_group_as_admin(db, chat_id, user_id):
    """Проверяет, что это группа и что я в ней админ. Возвращает группу."""
    me = await get_member(db, chat_id, user_id)
    chat = await db.get(Chat, chat_id)
    if not chat.is_group:
        raise HTTPException(status_code=400, detail='Это не группа')
    if not me.is_admin:
        raise HTTPException(status_code=403, detail='Это может делать только админ группы')
    return chat


async def tell_members_chat_changed(db, chat_id, extra_user_ids=()):
    """Говорит всем участникам (и ещё указанным людям), что чат изменился, пусть обновят список."""
    member_ids = list(await get_member_ids(db, chat_id)) + list(extra_user_ids)
    await send_to_users(set(member_ids), {'type': 'chat_updated', 'chat_id': chat_id})


# ---------- Создание чатов ----------

@router.post('/private', response_model=ChatResponse)
async def create_private_chat(
    data: CreatePrivateChatRequest,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    """Личный чат с одним человеком. Если такой уже есть, вернёт его (как в WhatsApp)."""
    if data.user_id == user_id:
        raise HTTPException(status_code=400, detail='Нельзя создать чат с самим собой')

    # ищем среди моих личных чатов тот, где уже есть этот человек
    result = await db.execute(
        select(Chat)
        .join(ChatMember, ChatMember.chat_id == Chat.id)
        .where(Chat.is_group == False, ChatMember.user_id == user_id)
    )
    for chat in result.scalars().all():
        other = await db.execute(
            select(ChatMember).where(ChatMember.chat_id == chat.id, ChatMember.user_id == data.user_id)
        )
        if other.scalars().first():
            return chat

    chat = Chat(is_group=False, created_by=user_id)
    db.add(chat)
    await db.flush()   # чтобы получить chat.id
    db.add(ChatMember(chat_id=chat.id, user_id=user_id))
    db.add(ChatMember(chat_id=chat.id, user_id=data.user_id))
    await db.commit()

    await tell_members_chat_changed(db, chat.id)
    return chat


@router.post('/group', response_model=ChatResponse)
async def create_group(
    data: CreateGroupRequest,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    """Создать группу. Тот, кто создал, становится админом."""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Назовите группу')

    member_ids = set(data.member_ids)
    member_ids.add(user_id)
    if len(member_ids) < 2:
        raise HTTPException(status_code=400, detail='Добавьте хотя бы одного участника')
    if len(member_ids) > MAX_GROUP_SIZE:
        raise HTTPException(status_code=400, detail=f'В группе не больше {MAX_GROUP_SIZE} человек')

    chat = Chat(name=name, is_group=True, created_by=user_id)
    db.add(chat)
    await db.flush()
    for member_id in member_ids:
        db.add(ChatMember(chat_id=chat.id, user_id=member_id, is_admin=(member_id == user_id)))
    await db.commit()

    await tell_members_chat_changed(db, chat.id)
    return chat


# ---------- Список чатов ----------

@router.get('/', response_model=list[ChatListItemResponse])
async def get_my_chats(db=Depends(get_db), user_id=Depends(get_current_user)):
    """Главный экран: все мои чаты, последнее сообщение и сколько непрочитанных."""
    # 1. мои чаты
    result = await db.execute(
        select(Chat)
        .join(ChatMember, ChatMember.chat_id == Chat.id)
        .where(ChatMember.user_id == user_id)
    )
    chats = result.scalars().all()
    if not chats:
        return []
    chat_ids = [chat.id for chat in chats]

    # 2. последнее сообщение в каждом чате
    newest_ids = (
        select(func.max(Message.id))
        .where(Message.chat_id.in_(chat_ids))
        .group_by(Message.chat_id)
    )
    result = await db.execute(select(Message).where(Message.id.in_(newest_ids)))
    last_messages = {message.chat_id: message for message in result.scalars().all()}

    # 3. сколько непрочитанных (чужие сообщения новее моего last_read_message_id)
    result = await db.execute(
        select(Message.chat_id, func.count(Message.id))
        .join(ChatMember, ChatMember.chat_id == Message.chat_id)
        .where(
            ChatMember.user_id == user_id,
            Message.chat_id.in_(chat_ids),
            Message.id > ChatMember.last_read_message_id,
            Message.sender_id != user_id,
            Message.is_deleted == False,
        )
        .group_by(Message.chat_id)
    )
    unread_counts = {chat_id: count for chat_id, count in result.all()}

    # 4. в личных чатах узнаём, кто собеседник
    private_ids = [chat.id for chat in chats if not chat.is_group]
    other_users = {}
    if private_ids:
        result = await db.execute(
            select(ChatMember.chat_id, ChatMember.user_id)
            .where(ChatMember.chat_id.in_(private_ids), ChatMember.user_id != user_id)
        )
        other_users = {chat_id: other_id for chat_id, other_id in result.all()}

    rows = []
    for chat in chats:
        last_message = last_messages.get(chat.id)
        item = ChatListItemResponse(
            id=chat.id,
            name=chat.name,
            is_group=chat.is_group,
            other_user_id=other_users.get(chat.id),
            last_message=last_message,
            unread_count=unread_counts.get(chat.id, 0),
        )
        sort_date = last_message.created_date if last_message else chat.created_date
        rows.append((sort_date, item))

    rows.sort(key=lambda row: row[0], reverse=True)   # свежие чаты сверху
    return [item for sort_date, item in rows]


# ---------- Участники и управление группой ----------

@router.get('/{chat_id}/members', response_model=list[MemberResponse])
async def get_members(chat_id: int, db=Depends(get_db), user_id=Depends(get_current_user)):
    await get_member(db, chat_id, user_id)
    result = await db.execute(select(ChatMember).where(ChatMember.chat_id == chat_id))
    return result.scalars().all()


@router.patch('/{chat_id}', response_model=ChatResponse)
async def rename_group(
    chat_id: int,
    data: RenameGroupRequest,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    chat = await get_group_as_admin(db, chat_id, user_id)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='Название не может быть пустым')
    chat.name = name
    await db.commit()

    await tell_members_chat_changed(db, chat_id)
    return chat


@router.post('/{chat_id}/members')
async def add_member(
    chat_id: int,
    data: AddMemberRequest,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    await get_group_as_admin(db, chat_id, user_id)

    member_ids = await get_member_ids(db, chat_id)
    if data.user_id in member_ids:
        raise HTTPException(status_code=400, detail='Он уже в группе')
    if len(member_ids) >= MAX_GROUP_SIZE:
        raise HTTPException(status_code=400, detail=f'В группе не больше {MAX_GROUP_SIZE} человек')

    db.add(ChatMember(chat_id=chat_id, user_id=data.user_id))
    await db.commit()

    await tell_members_chat_changed(db, chat_id)
    return {'status': 'ok'}


@router.delete('/{chat_id}/members/{member_id}')
async def remove_member(
    chat_id: int,
    member_id: int,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    await get_group_as_admin(db, chat_id, user_id)
    if member_id == user_id:
        raise HTTPException(status_code=400, detail='Чтобы выйти самому, используйте /leave')

    result = await db.execute(
        select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == member_id)
    )
    member = result.scalars().first()
    if member is None:
        raise HTTPException(status_code=404, detail='Такого участника нет')

    await db.delete(member)
    await db.commit()

    # уведомляем оставшихся и самого удалённого (чтобы у него чат пропал)
    await tell_members_chat_changed(db, chat_id, extra_user_ids=[member_id])
    return {'status': 'ok'}


@router.post('/{chat_id}/members/{member_id}/make-admin')
async def make_admin(
    chat_id: int,
    member_id: int,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    await get_group_as_admin(db, chat_id, user_id)

    result = await db.execute(
        select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == member_id)
    )
    member = result.scalars().first()
    if member is None:
        raise HTTPException(status_code=404, detail='Такого участника нет')

    member.is_admin = True
    await db.commit()

    await tell_members_chat_changed(db, chat_id)
    return {'status': 'ok'}


@router.post('/{chat_id}/leave')
async def leave_group(chat_id: int, db=Depends(get_db), user_id=Depends(get_current_user)):
    me = await get_member(db, chat_id, user_id)
    chat = await db.get(Chat, chat_id)
    if not chat.is_group:
        raise HTTPException(status_code=400, detail='Из личного чата выйти нельзя')

    old_member_ids = await get_member_ids(db, chat_id)

    await db.delete(me)
    await db.flush()

    result = await db.execute(
        select(ChatMember).where(ChatMember.chat_id == chat_id).order_by(ChatMember.id)
    )
    left = result.scalars().all()
    if not left:
        await db.delete(chat)               # никого не осталось: удаляем группу
    elif not any(member.is_admin for member in left):
        left[0].is_admin = True             # админ ушёл: самый старый участник становится админом
    await db.commit()

    await send_to_users(set(old_member_ids), {'type': 'chat_updated', 'chat_id': chat_id})
    return {'status': 'ok'}
