from pathlib import Path

from pydantic.v1 import BaseSettings
from starlette.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name = 'crypto_scanner'
    debug = True
    host = 'localhost'
    port = 8000

    templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
    
    # TODO: set session key before deploy
    SESSION_SECRET_KEY = ''

    class Config:
        env_file = BASE_DIR / '.env'
        env_file_encoding = 'utf-8'

cfg = Settings()
