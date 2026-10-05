import os
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from chat_service.api.authentication import get_current_user
from chat_service.api.authorization import get_chat_member
from chat_service.config import UPLOAD_DIR, MAX_FILE_SIZE, MAX_FILE_SIZE_MB
from chat_service.database.db import get_db

router = APIRouter(tags=['Files'])


def get_message_type(content_type):
    if content_type.startswith('image/'):
        return 'image'
    if content_type.startswith('audio/'):
        return 'voice'
    if content_type.startswith('video/'):
        return 'video'
    return 'file'


async def save_file_to_disk(chat_id, file):
    if not file.size:
        raise HTTPException(status_code=400, detail='Файл пустой')
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f'Файл больше {MAX_FILE_SIZE_MB} МБ')

    original_name = os.path.basename(file.filename or 'file')[-100:]
    saved_name = uuid.uuid4().hex + '_' + original_name  # уникальное имя файла

    folder = os.path.join(UPLOAD_DIR, str(chat_id))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, saved_name), 'wb') as f:
        await run_in_threadpool(shutil.copyfileobj, file.file, f)

    content_type = file.content_type or 'application/octet-stream'
    return {
        'message_type': get_message_type(content_type),
        'file_url': f'/files/{chat_id}/{saved_name}',
        'file_name': original_name,
        'file_size': file.size,
    }


def delete_file_from_disk(file_url):
    # удаляем файл с диска
    parts = file_url.split('/')
    path = os.path.join(UPLOAD_DIR, parts[2], os.path.basename(parts[3]))
    if os.path.isfile(path):
        os.remove(path)


@router.get('/files/{chat_id}/{filename}')
async def download_file(
    chat_id: int,
    filename: str,
    db=Depends(get_db),
    user_id=Depends(get_current_user),
):
    await get_chat_member(db, chat_id, user_id)  # проверяем участника чата

    path = os.path.join(UPLOAD_DIR, str(chat_id), os.path.basename(filename))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail='Файл не найден')

    return FileResponse(
        path,
        headers={
            'Content-Security-Policy': 'sandbox',
            'X-Content-Type-Options': 'nosniff',
        },
    )