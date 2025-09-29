from pathlib import Path

from pydantic.v1 import BaseSettings
from starlette.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name = 'crypto_scanner'
    debug = True
    host = 'localhost'
    port = 8000
    database_user = 'crypto_scanner'
    database_password = 'crypto_scanner'
    database_host = 'localhost'
    database_port = 5432
    database_name = 'crypto_scanner'
    # database_user: str = ''
    # database_password: str = ''
    # database_host: str = 'localhost'
    # database_port: int = 5432
    # database_name: str = ''

    templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
    
    # TODO: set session key before deploy
    SESSION_SECRET_KEY = ''
    
    @property
    def DATABASE(self):
        return {
            'user': self.database_user,
            'password': self.database_password,
            'host': self.database_host,
            'port': self.database_port,
            'database': self.database_name,
        }

    class Config:
        env_file = BASE_DIR / '.env'
        env_file_encoding = 'utf-8'

cfg = Settings()
