import uvicorn

from conf import cfg
from core.app import app


def run_server():
    uvicorn.run(app, host='0.0.0.0', port=cfg.port, reload=False)


if __name__ == "__main__":
    run_server()
