from fastapi import APIRouter, Request
from starlette.responses import HTMLResponse

from conf import cfg


router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def home(request: Request):

    return cfg.templates.TemplateResponse("index.html", {"request": request})
