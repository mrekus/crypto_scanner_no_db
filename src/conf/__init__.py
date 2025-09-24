from pathlib import Path

from pydantic.v1 import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name = 'crypto_scanner'
    debug = True
    host = 'localhost'
    port = 8000
    # TODO: set session key before deploy
    SESSION_SECRET_KEY = ''

cfg = Settings()
