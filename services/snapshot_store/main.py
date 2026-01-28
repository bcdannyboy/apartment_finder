import uvicorn

from services.common.local_bind import ensure_local_bind
from services.snapshot_store.app import app


def run(host: str = "127.0.0.1", port: int = 8002) -> None:
    ensure_local_bind(host)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
