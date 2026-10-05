from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
import httpx

from chat_service.config import AUTH_SERVICE_URL


oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/login')


async def get_current_user(token: str = Depends(oauth2_scheme)):
    # Получаем user_id и role из Django
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(
                f'{AUTH_SERVICE_URL}/auth/verify/',
                headers={'Authorization': f'Bearer {token}'},
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail='Auth service недоступен')

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail='Invalid or expired token')

    if response.status_code != 200:
        raise HTTPException(status_code=503, detail='Auth service error')

    data = response.json()

    # Возвращаем данные пользователя для Chat Server
    return {
        'id': int(data['id']),
        'username': data['username'],
        'role': data['role'],
    }