from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.hash import bcrypt
from sqlalchemy.orm import Session

from conf import cfg
from core.database import get_db
from models.users import User, ROLE

router = APIRouter()


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return cfg.templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
def register(
        username: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db)):
    existing = db.query(User).filter_by(username=username).first()
    if existing:
        return HTMLResponse("User exists", status_code=400)
    role = ROLE.USER
    hashed = bcrypt.hash(password)
    user = User(username=username, hashed_password=hashed, role=role)
    db.add(user)
    db.commit()
    return RedirectResponse("/login", status_code=303)
