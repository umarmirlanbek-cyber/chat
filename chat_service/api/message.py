from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, func
from chat_service.api.authentication import get_current_user
from chat_service.api.authorization import get_chat_member, get_chat_member_ids
from chat_service.api.file import save_file_to_disk, delete_file_from_disk
from chat_service.api.websocket import send_to_users
from chat_service.database.db import get_db
from chat_service.database.models import Message
from chat_service.database.schema import MessageResponse,SendTextMessageRequest,EditMessageRequest,MarkAsReadRequest

router = APIRouter(tags=['Messages'])

MAX_TEXT_LENGTH = 4000


def message_to_dict(message):
    return MessageResponse.model_validate(message).model_dump(mode='json')


def clean_text(text):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail='Сообщение пустое')
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(status_code=400, detail=f'Сообщение длиннее {MAX_TEXT_LENGTH} символов')
    return text


async def check_reply(db, chat_id, reply_to_id):
    if reply_to_id is None:
        return
    original = await db.get(Message, reply_to_id)
    if original is None or original.chat_id != chat_id:
        raise HTTPException(status_code=400, detail='Сообщение, на которое вы отвечаете, не найдено')


async def save_and_send(db, chat_id, sender_id, **fields):
    message = Message(chat_id=chat_id, sender_id=sender_id, **fields)
    db.add(message)
    await db.commit()

    member_ids = await get_chat_member_ids(db, chat_id)
    await send_to_users(member_ids, {'type': 'new_message', 'message': message_to_dict(message)})
    return message


@router.post('/chats/{chat_id}/messages', response_model=MessageResponse)
async def send_text_message(
    chat_id: int,
    data: SendTextMessageRequest,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    text = clean_text(data.text)
    await get_chat_member(db, chat_id, user_id)  # проверяем участника чата
    await check_reply(db, chat_id, data.reply_to_id)
    return await save_and_send(
        db, chat_id, user_id,
        message_type='text', text=text, reply_to_id=data.reply_to_id,
    )


@router.post('/chats/{chat_id}/messages/file', response_model=MessageResponse)
async def send_file_message(
    chat_id: int,
    file: UploadFile = File(...),
    caption: str = Form(None),
    duration_seconds: float = Form(None),
    reply_to_id: int = Form(None),
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    await get_chat_member(db, chat_id, user_id)  # проверяем участника чата
    await check_reply(db, chat_id, reply_to_id)

    file_info = await save_file_to_disk(chat_id, file)
    text = caption.strip() if caption else None
    return await save_and_send(
        db, chat_id, user_id,
        text=text, duration_seconds=duration_seconds, reply_to_id=reply_to_id,
        **file_info,
    )


@router.get('/chats/{chat_id}/messages', response_model=list[MessageResponse])
async def get_messages(
    chat_id: int,
    limit: int = 50,
    before_id: int = None,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    await get_chat_member(db, chat_id, user_id)  # проверяем участника чата

    if limit > 100:
        limit = 100

    query = select(Message).where(Message.chat_id == chat_id)
    if before_id:
        query = query.where(Message.id < before_id)
    query = query.order_by(Message.id.desc()).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.patch('/messages/{message_id}', response_model=MessageResponse)
async def edit_message(
    message_id: int,
    data: EditMessageRequest,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    message = await db.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail='Сообщение не найдено')

    await get_chat_member(db, message.chat_id, user_id)  # проверяем участника чата

    if message.sender_id != user_id:
        raise HTTPException(status_code=403, detail='Можно менять только свои сообщения')
    if message.is_deleted or message.file_url:
        raise HTTPException(status_code=400, detail='Это сообщение нельзя изменить')

    message.text = clean_text(data.text)
    message.is_edited = True
    await db.commit()

    member_ids = await get_chat_member_ids(db, message.chat_id)
    await send_to_users(member_ids, {'type': 'message_edited', 'message': message_to_dict(message)})
    return message


@router.delete('/messages/{message_id}')
async def delete_message(
    message_id: int,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    message = await db.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail='Сообщение не найдено')

    member = await get_chat_member(db, message.chat_id, user_id)  # получаем участника чата

    if message.sender_id != user_id and not member.is_admin:
        raise HTTPException(status_code=403, detail='Нельзя удалить чужое сообщение')
    if message.is_deleted:
        return {'status': 'ok'}

    if message.file_url:
        delete_file_from_disk(message.file_url)

    message.is_deleted = True
    message.text = None
    message.file_url = None
    message.file_name = None
    message.file_size = None
    message.duration_seconds = None
    await db.commit()

    member_ids = await get_chat_member_ids(db, message.chat_id)
    await send_to_users(member_ids, {
        'type': 'message_deleted', 'chat_id': message.chat_id, 'message_id': message.id,
    })
    return {'status': 'ok'}


@router.post('/chats/{chat_id}/read')
async def mark_as_read(
    chat_id: int,
    data: MarkAsReadRequest,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    member = await get_chat_member(db, chat_id, user_id)  # получаем участника чата

    result = await db.execute(select(func.max(Message.id)).where(Message.chat_id == chat_id))
    newest_id = result.scalar() or 0
    last_read_id = min(data.last_message_id, newest_id)

    if last_read_id > member.last_read_message_id:
        member.last_read_message_id = last_read_id
        await db.commit()

        member_ids = await get_chat_member_ids(db, chat_id)
        await send_to_users(member_ids, {
            'type': 'messages_read', 'chat_id': chat_id,
            'user_id': user_id, 'last_message_id': last_read_id,
        })
    return {'status': 'ok'}