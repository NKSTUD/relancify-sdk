import httpx
import pytest

from relancify_sdk.auth import AuthConfig
from relancify_sdk.errors import ApiError
from relancify_sdk.http import HttpClient
from relancify_sdk.resources.runtime import RuntimeResource


def test_auth_config_repr_hides_credentials() -> None:
    auth = AuthConfig(api_key="secret-api-key", bearer="secret-bearer")

    rendered = repr(auth)

    assert "secret-api-key" not in rendered
    assert "secret-bearer" not in rendered


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://api.relancify.com/api/v1",
        "https://user:password@api.relancify.com/api/v1",
        "http://api.relancify.com/api/v1",
    ],
)
def test_http_client_rejects_unsafe_base_urls(base_url: str) -> None:
    with pytest.raises(ValueError):
        HttpClient(base_url, AuthConfig(api_key="secret"))


def test_http_client_allows_loopback_http() -> None:
    client = HttpClient(
        "http://127.0.0.1:8000/api/v1",
        AuthConfig(api_key="secret"),
    )

    client.close()


def test_http_client_does_not_follow_redirects_with_credentials() -> None:
    requests: list[httpx.Request] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            headers={"location": "https://attacker.example/collect"},
            request=request,
        )

    client = HttpClient(
        "https://api.relancify.com/api/v1",
        AuthConfig(api_key="secret"),
    )
    client._client.close()
    client._client = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(redirect),
        follow_redirects=False,
    )

    with pytest.raises(ApiError) as error:
        client.request("GET", "/agents")

    client.close()
    assert error.value.code == "unsafe_redirect"
    assert len(requests) == 1
    assert requests[0].headers["x-api-key"] == "secret"


def test_runtime_resource_rejects_non_uuid_session_paths() -> None:
    client = HttpClient(
        "https://api.relancify.com/api/v1",
        AuthConfig(api_key="secret"),
    )
    runtime = RuntimeResource(client)

    with pytest.raises(ValueError, match="session_id"):
        runtime.get_session("../../api-keys")

    client.close()
