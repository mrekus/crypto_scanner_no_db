from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from conf import cfg

# TODO: import routers

app = FastAPI(
    title=cfg.app_name.capitalize(),
    debug=cfg.debug,
    on_startup=[],
    on_shutdown=[],
)

app.add_middleware(SessionMiddleware, secret_key=cfg.SESSION_SECRET_KEY)

# TODO: include routers
