from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from apps import default, calculator, openai
from conf import cfg


app = FastAPI(
    title=cfg.app_name.capitalize(),
    debug=cfg.debug,
    on_startup=[],
    on_shutdown=[],
)

app.add_middleware(SessionMiddleware, secret_key=cfg.SESSION_SECRET_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(default.router)
app.include_router(calculator.router)
app.include_router(openai.router)
