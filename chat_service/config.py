import os
from dotenv import load_dotenv

load_dotenv()


SECRET_KEY = os.environ['SECRET_KEY']
ALGORITHM = os.getenv('ALGORITHM', 'HS256')

JWT_USER_CLAIM = os.getenv('JWT_USER_CLAIM', 'user_id')

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost/chat_service')
DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')

UPLOAD_DIR = os.getenv('UPLOAD_DIR', 'uploads')
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '50'))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024


AUTH_SERVICE_URL = os.environ['AUTH_SERVICE_URL']