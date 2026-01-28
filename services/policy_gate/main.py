import uvicorn

from services.common.local_bind import ensure_local_bind
from services.policy_gate.app import app


def run(host: str = "127.0.0.1", port: int = 8001) -> None:
    ensure_local_bind(host)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
