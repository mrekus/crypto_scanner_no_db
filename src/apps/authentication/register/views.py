from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from passlib.hash import argon2
from pydantic import BaseModel
from sqlalchemy.orm import Session

from conf import cfg
from core.database import get_db
from models.users import User, ROLE

router = APIRouter()


class RegisterData(BaseModel):
    username: str
    password: str


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return cfg.templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
def register(data: RegisterData, db: Session = Depends(get_db)):
    existing = db.query(User).filter_by(username=data.username).first()
    if existing:
        return JSONResponse({"error": "User exists"}, status_code=400)

    hashed = argon2.hash(data.password)
    user = User(username=data.username, hashed_password=hashed, role=ROLE.USER)
    db.add(user)
    db.commit()

    return RedirectResponse("/login", status_code=303)
