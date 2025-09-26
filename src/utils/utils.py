import importlib
import os
from pathlib import Path

from fastapi import Depends
from sqlalchemy.orm import Session
from starlette.requests import Request

from core.database import get_db
from models.users import User


def import_all_models():
    project_root = Path(__file__).resolve().parent.parent
    models_dir = project_root / 'models'
    for file in os.listdir(models_dir):
        if file.endswith('.py') and file != '__init__.py':
            module_name = f'models.{file[:-3]}'
            importlib.import_module(module_name)


def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get('user_id')
    if not user_id:
        return None
    return db.query(User).filter_by(id=user_id).first()
