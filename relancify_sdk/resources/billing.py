from typing import Any, Dict

from relancify_sdk.http import HttpClient


class BillingResource:
    """Read-only billing endpoints for tenant dashboard and reconciliation."""

    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def summary(self) -> Dict[str, Any]:
        return self._client.request("GET", "/billing/summary")

    def usage_ledger(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        return self._client.request(
            "GET",
            f"/billing/usage-ledger?page={int(page)}&page_size={int(page_size)}",
        )

    def credit_transactions(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        return self._client.request(
            "GET",
            f"/billing/credit-transactions?page={int(page)}&page_size={int(page_size)}",
        )
