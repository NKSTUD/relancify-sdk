import httpx
import pytest

from relancify_sdk.auth import AuthConfig
from relancify_sdk.errors import ApiError
from relancify_sdk.http import HttpClient


class SequenceFakeClient:
    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls = 0

    def request(self, method, path, json=None, headers=None):
        self.calls += 1
        return self._responses.pop(0)


def _http_client(responses) -> tuple[HttpClient, SequenceFakeClient]:
    client = HttpClient(base_url="https://api.test", auth=AuthConfig())
    fake = SequenceFakeClient(responses)
    client._client = fake
    return client, fake


def _rate_limited(retry_after: int = 1) -> httpx.Response:
    return httpx.Response(
        429,
        headers={"Retry-After": str(retry_after)},
        json={"detail": "rate limited"},
    )


def test_429_then_200_succeeds(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr("relancify_sdk.http.time.sleep", sleeps.append)
    client, fake = _http_client(
        [_rate_limited(retry_after=2), httpx.Response(200, json={"ok": True})]
    )

    response = client.request_response("GET", "/v1/ping")

    assert response.status_code == 200
    assert fake.calls == 2
    assert sleeps == [2]


def test_three_429s_raises_api_error(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr("relancify_sdk.http.time.sleep", sleeps.append)
    client, fake = _http_client([_rate_limited(), _rate_limited(), _rate_limited()])

    with pytest.raises(ApiError) as excinfo:
        client.request_response("GET", "/v1/ping")

    assert excinfo.value.status_code == 429
    assert fake.calls == 3
    assert sleeps == [1, 1]
