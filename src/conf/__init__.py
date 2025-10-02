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
    
    ERC20_TOKEN_METADATA = {
      '0x068693929b9b6a8444671b4280cc79350d38244d': {
        'decimals': 9,
        'logo': None,
        'name': 'DOJ',
        'symbol': 'DOJ'
      },
      '0x0fab0827824b152dbda17bb8429a425ffb89334a': {
        'decimals': 18,
        'logo': None,
        'name': 'NapierV2-PT-Pareto staked USP@29/9/2025',
        'symbol': 'PT-sUSP@29/9/2025'
      },
      '0x12996c7b23c4012149bf9f5663ff9aa08a9cf2e4': {
        'decimals': 18,
        'logo': 'https://static.alchemyapi.io/images/assets/31866.png',
        'name': 'White Yorkshire',
        'symbol': 'WSH'
      },
      '0x142197e542380737024d122b291d17478d1f81d0': {
        'decimals': 18,
        'logo': None,
        'name': 'Cyrus Sargon',
        'symbol': 'CSS'
      },
      '0x161a4682a69a0cf35713268f1348a068d745a5d2': {
        'decimals': 18,
        'logo': None,
        'name': 'Stars',
        'symbol': 'Stars'
      },
      '0x2088933e4242cc7020fb8fb18481c7d22f3e8a55': {
        'decimals': 18,
        'logo': None,
        'name': 'XMOVE',
        'symbol': 'XMOVE'
      },
      '0x219ea3ed07b33266d6befc2afbc35f82a63a6da7': {
        'decimals': 9,
        'logo': None,
        'name': 'HU LE ZHI',
        'symbol': 'HULEZHI'
      },
      '0x32cd5e50ca6b4640748f7d9a40c5a13f727feb4f': {
        'decimals': 9,
        'logo': None,
        'name': 'CoreChain',
        'symbol': 'CORE'
      },
      '0x544a6c0fa9fe5f34ba410a4d5d7165a733b6e971': {
        'decimals': 8,
        'logo': None,
        'name': 'Fusion Systems',
        'symbol': 'FUSION'
      },
      '0x5f5166c4fdb9055efb24a7e75cc1a21ca8ca61a3': {
        'decimals': 9,
        'logo': 'https://static.alchemyapi.io/images/assets/26984.png',
        'name': 'AI-X',
        'symbol': 'X'
      },
      '0x6051c1354ccc51b4d561e43b02735deae64768b8': {
        'decimals': 18,
        'logo': 'https://static.alchemyapi.io/images/assets/7441.png',
        'name': 'yRise Finance',
        'symbol': 'YRISE'
      },
      '0x660b045699ecc049036c0db165bcb99fc22a2d51': {
        'decimals': 18,
        'logo': None,
        'name': 'Meta Boost',
        'symbol': 'MB'
      },
      '0x66a3c2fa3e467aa586e90912f977e648589cabaf': {
        'decimals': 8,
        'logo': None,
        'name': 'AI Chain Coin',
        'symbol': 'AICC'
      },
      '0x8be3460a480c80728a8c4d7a5d5303c85ba7b3b9': {
        'decimals': 18,
        'logo': None,
        'name': 'Staked ENA',
        'symbol': 'sENA'
      },
      '0x9c2d193745af9a596dea384814897f2a952d8d39': {
        'decimals': 18,
        'logo': None,
        'name': 'NapierV2-YT-Pareto staked USP@29/9/2025',
        'symbol': 'YT-sUSP@29/9/2025'
      },
      '0x9fc29658a3161cee9a58754193edbea7edafce3e': {
        'decimals': 9,
        'logo': None,
        'name': 'XPRESSIONS',
        'symbol': 'XPRESSIONS'
      },
      '0xb1d1eae60eea9525032a6dcb4c1ce336a1de71be': {
        'decimals': 18,
        'logo': None,
        'name': 'Derive',
        'symbol': 'DRV'
      },
      '0xbc78fa925efefe37088c11bb6ad6dc7933f86328': {
        'decimals': 18,
        'logo': None,
        'name': 'COCO',
        'symbol': 'DODO KILLER'
      },
      '0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa': {
        'decimals': 18,
        'logo': 'https://static.alchemyapi.io/images/assets/29035.png',
        'name': 'Mantle Staked Ether',
        'symbol': 'METH'
      },
      '0xdaf27d9f6d7a6ff106ecb6d681bd8b20fd8e27a3': {
        'decimals': 9,
        'logo': None,
        'name': 'Rip Hurricane',
        'symbol': 'HURRICANE'
      },
      '0xe54463c9d067453f7a3cf9409b1b051a5a7722e6': {
        'decimals': 9,
        'logo': None,
        'name': 'Microsoft Bob',
        'symbol': 'BOB'
      }
    }
    
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
