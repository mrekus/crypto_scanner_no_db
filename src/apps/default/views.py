from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from starlette.responses import HTMLResponse

from conf import cfg
from core.database import get_db
from utils.utils import get_current_user

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    return cfg.templates.TemplateResponse("index.html", {"request": request, "user": user})
