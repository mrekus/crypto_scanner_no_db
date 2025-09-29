from fastapi import APIRouter, Depends, Request
from starlette.responses import HTMLResponse

from conf import cfg
from models.users import User
from utils.utils import require_user

router = APIRouter()


@router.get("/calculator", response_class=HTMLResponse)
def home(request: Request, user: User = Depends(require_user)):
    if isinstance(user, HTMLResponse):
        return user

    return cfg.templates.TemplateResponse('calculator.html', {'request': request})
