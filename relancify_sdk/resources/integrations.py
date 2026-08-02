from __future__ import annotations

from typing import Any, Dict, List, Optional

from relancify_sdk.http import AsyncHttpClient, HttpClient


class IntegrationsResource:
    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list_catalog(self) -> List[Dict[str, Any]]:
        return self._client.request("GET", "/integrations/catalog")

    def get_stripe_connection(self) -> Dict[str, Any]:
        return self._client.request(
            "GET",
            "/integrations/templates/stripe/connection",
        )

    def upsert_stripe_connection(
        self,
        *,
        name: str,
        api_key: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self._client.request(
            "PUT",
            "/integrations/templates/stripe/connection",
            json={
                "name": name,
                "api_key": api_key,
                "allowed_tools": list(allowed_tools or []),
            },
        )


class AsyncIntegrationsResource:
    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list_catalog(self) -> List[Dict[str, Any]]:
        return await self._client.request("GET", "/integrations/catalog")

    async def get_stripe_connection(self) -> Dict[str, Any]:
        return await self._client.request(
            "GET",
            "/integrations/templates/stripe/connection",
        )

    async def upsert_stripe_connection(
        self,
        *,
        name: str,
        api_key: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return await self._client.request(
            "PUT",
            "/integrations/templates/stripe/connection",
            json={
                "name": name,
                "api_key": api_key,
                "allowed_tools": list(allowed_tools or []),
            },
        )
