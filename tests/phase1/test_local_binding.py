import pytest

from services.common.local_bind import LocalBindError, ensure_local_bind


def test_local_binding_accepts_localhost():
    ensure_local_bind("127.0.0.1")
    ensure_local_bind("localhost")
    ensure_local_bind("::1")


def test_local_binding_rejects_non_local():
    with pytest.raises(LocalBindError):
        ensure_local_bind("0.0.0.0")
