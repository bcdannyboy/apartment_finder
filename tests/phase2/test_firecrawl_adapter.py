from services.acquisition.errors import AdapterValidationError
from services.acquisition.firecrawl_adapter import FirecrawlAdapter
from services.acquisition.models import FirecrawlRequest, FirecrawlResponse
from services.common.hashes import sha256_text


class FakeFirecrawlClient:
    def __init__(self, response: FirecrawlResponse) -> None:
        self.response = response
        self.calls = 0

    def fetch(self, request: FirecrawlRequest) -> FirecrawlResponse:
        self.calls += 1
        return self.response


def test_firecrawl_rejects_missing_change_tracking(snapshot_store, adapter_log):
    response = FirecrawlResponse(
        url="https://example.com",
        http_status=200,
        formats={"html": True, "markdown": True},
        fetched_at="2026-01-28T00:00:00Z",
        raw_content="<html>hi</html>",
    )
    client = FakeFirecrawlClient(response)
    adapter = FirecrawlAdapter(client=client, snapshot_store=snapshot_store, adapter_log=adapter_log)

    request = FirecrawlRequest(
        schema_version="v1",
        url="https://example.com",
        formats={"html": True, "markdown": True},
        change_tracking=None,
    )
    try:
        adapter.fetch_and_store(task_id="task-1", source_id="source-1", request=request)
    except AdapterValidationError:
        pass
    else:
        assert False, "Expected AdapterValidationError"
    assert client.calls == 0


def test_firecrawl_rejects_unsupported_format(snapshot_store):
    response = FirecrawlResponse(
        url="https://example.com",
        http_status=200,
        formats={"html": True, "markdown": True},
        fetched_at="2026-01-28T00:00:00Z",
        raw_content="<html>hi</html>",
    )
    client = FakeFirecrawlClient(response)
    adapter = FirecrawlAdapter(client=client, snapshot_store=snapshot_store)

    request = FirecrawlRequest(
        schema_version="v1",
        url="https://example.com",
        formats={"html": True, "markdown": True, "unsupported": True},
        change_tracking={"mode": "diff"},
    )
    try:
        adapter.fetch_and_store(task_id="task-1", source_id="source-1", request=request)
    except AdapterValidationError:
        pass
    else:
        assert False, "Expected AdapterValidationError"
    assert client.calls == 0


def test_firecrawl_content_hash_fallback(snapshot_store):
    response = FirecrawlResponse(
        url="https://example.com",
        http_status=200,
        formats={"html": True, "markdown": True},
        fetched_at="2026-01-28T00:00:00Z",
        raw_content="<html>alpha</html>",
    )
    client = FakeFirecrawlClient(response)
    adapter = FirecrawlAdapter(client=client, snapshot_store=snapshot_store)

    request = FirecrawlRequest(
        schema_version="v1",
        url="https://example.com",
        formats={"html": True, "markdown": True},
        change_tracking={"mode": "diff"},
    )
    snapshot = adapter.fetch_and_store(task_id="task-1", source_id="source-1", request=request)
    assert snapshot.content_hash == sha256_text("<html>alpha</html>")


def test_firecrawl_change_tracking_stored(snapshot_store):
    response = FirecrawlResponse(
        url="https://example.com",
        http_status=200,
        formats={"html": True, "markdown": True},
        fetched_at="2026-01-28T00:00:00Z",
        raw_content="<html>alpha</html>",
    )
    client = FakeFirecrawlClient(response)
    adapter = FirecrawlAdapter(client=client, snapshot_store=snapshot_store)

    request = FirecrawlRequest(
        schema_version="v1",
        url="https://example.com",
        formats={"html": True, "markdown": True},
        change_tracking={"mode": "diff"},
    )
    snapshot = adapter.fetch_and_store(task_id="task-1", source_id="source-1", request=request)
    assert snapshot.change_tracking == {"mode": "diff"}
