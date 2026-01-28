LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class LocalBindError(ValueError):
    pass


def ensure_local_bind(host: str) -> None:
    if host not in LOCAL_HOSTS:
        raise LocalBindError(
            f"Local-only binding required; received host={host!r}"
        )
