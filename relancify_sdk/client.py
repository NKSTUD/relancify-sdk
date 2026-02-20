from typing import Optional

from relancify_sdk.auth import AuthConfig
from relancify_sdk.http import HttpClient
from relancify_sdk.resources.agents import AgentsResource
from relancify_sdk.resources.api_keys import ApiKeysResource
from relancify_sdk.resources.operations import OperationsResource
from relancify_sdk.resources.runtime import RuntimeResource
from relancify_sdk.resources.users import UsersResource
from relancify_sdk.resources.voices import VoicesResource


class RelancifyClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        api_key: Optional[str] = None,
        bearer: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        auth = AuthConfig(api_key=api_key, bearer=bearer)
        self._http = HttpClient(base_url=base_url, auth=auth, timeout=timeout)
        self.agents = AgentsResource(self._http)
        self.api_keys = ApiKeysResource(self._http)
        self.operations = OperationsResource(self._http)
        self.runtime = RuntimeResource(self._http)
        self.users = UsersResource(self._http)
        self.voices = VoicesResource(self._http)

    def close(self) -> None:
        self._http.close()
