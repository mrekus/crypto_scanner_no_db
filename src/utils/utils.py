import importlib
import json
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.requests import Request

from conf import cfg
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


def require_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return cfg.templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Authentication required"},
            status_code=401
        )
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        return cfg.templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Invalid session"},
            status_code=401
        )

    return user


def load_json_file(file_path: str | Path) -> Any:
    base_path = Path(__file__).parent.parent
    file_path = base_path / file_path
    if not file_path.exists():
        raise FileNotFoundError(f'JSON file not found: {file_path}')

    with file_path.open('r', encoding='utf-8') as f:
        return json.load(f)
