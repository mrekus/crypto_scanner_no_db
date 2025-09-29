from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from apps import default
from apps.authentication import login, register
from conf import cfg


app = FastAPI(
    title=cfg.app_name.capitalize(),
    debug=cfg.debug,
    on_startup=[],
    on_shutdown=[],
)

app.add_middleware(SessionMiddleware, secret_key=cfg.SESSION_SECRET_KEY)

app.include_router(login.router)
app.include_router(register.router)
app.include_router(default.router)
