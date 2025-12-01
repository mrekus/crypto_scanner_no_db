import os
from pathlib import Path

from pydantic.v1 import BaseSettings
from starlette.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name = 'crypto_scanner'
    debug = True
    host = '0.0.0.0'
    port = int(os.getenv("PORT"))
    ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY")
    CG_API_KEY = os.getenv("CG_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    MAESTRO_API_KEY = os.getenv("MAESTRO_API_KEY")
    ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
    CORS_ENDPOINT = os.getenv("CORS_ENDPOINT")
    MAESTRO_API_URL = 'https://xbt-mainnet.gomaestro-api.org/v0'

    templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
    
    # TODO: set session key before deploy
    SESSION_SECRET_KEY = ''

    class Config:
        env_file = BASE_DIR / '.env'
        env_file_encoding = 'utf-8'

cfg = Settings()
