import datetime

from fastapi import APIRouter, Request
from fastapi.params import Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.hash import argon2
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from conf import cfg
from core.database import get_db
from models.users import User
from utils.utils import get_current_user

router = APIRouter()


class LoginData(BaseModel):
    username: str
    password: str


@router.get('/login', response_class=HTMLResponse)
def login_form(request: Request):
    return cfg.templates.TemplateResponse('calculator.html', {'request': request})


@router.post('/login')
def login(data: LoginData, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=data.username).first()
    if not user or not argon2.verify(data.password, user.hashed_password):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JSONResponse({'error': 'Invalid credentials'}, status_code=401)
        return RedirectResponse('/login', status_code=303)

    user.last_login = datetime.datetime.now(datetime.UTC)
    db.commit()

    request.session['user_id'] = user.id
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JSONResponse({'success': True})

    return RedirectResponse('/', status_code=303)


@router.get('/logout')
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url='/?logged_out=1', status_code=303)


@router.get('/me')
def read_current_user(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({'error': 'Not authenticated'}, status_code=401)
    return JSONResponse({
        'id': user.id,
        'username': user.username,
        'role': user.role.name,
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'last_login': user.last_login.isoformat() if user.last_login else None
    })
