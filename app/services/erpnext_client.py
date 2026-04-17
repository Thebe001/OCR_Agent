"""Small async ERPNext REST client."""

import asyncio
from typing import Any, Optional

import httpx

from app.config.tenants import TenantConfig
from app.models.errors import ErrorCode, MCPError


class ERPNextClient:
    MAX_RETRIES = 3

    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        self.base_url = tenant.site_url.rstrip("/")
        self.headers = {
            "Authorization": f"token {tenant.api_key}:{tenant.api_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get_resource(
        self,
        doctype: str,
        name: str,
        fields: Optional[list[str]] = None,
    ) -> dict:
        params = {"fields": str(fields)} if fields else None
        return await self._make_request(
            "GET",
            f"{self.base_url}/api/resource/{doctype}/{name}",
            params=params,
        )

    async def list_resource(
        self,
        doctype: str,
        filters: Optional[list] = None,
        fields: Optional[list[str]] = None,
        limit: int = 20,
        order_by: Optional[str] = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit_page_length": limit}
        if filters:
            params["filters"] = str(filters)
        if fields:
            params["fields"] = str(fields)
        if order_by:
            params["order_by"] = order_by

        result = await self._make_request(
            "GET",
            f"{self.base_url}/api/resource/{doctype}",
            params=params,
        )
        return result.get("data", [])

    async def create_resource(self, doctype: str, data: dict) -> dict:
        return await self._make_request(
            "POST",
            f"{self.base_url}/api/resource/{doctype}",
            json_data=data,
        )

    async def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=self.headers,
                        params=params,
                        json=json_data,
                    )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                raise MCPError(
                    ErrorCode.ERPNEXT_ERROR,
                    "Cannot connect to the system. Please try again later.",
                    f"{type(exc).__name__}: {exc}",
                ) from exc

            if response.status_code == 429 and attempt < self.MAX_RETRIES:
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code == 404:
                raise MCPError(ErrorCode.NOT_FOUND, "The requested resource was not found.", response.text[:500])
            if response.status_code in (401, 403):
                raise MCPError(
                    ErrorCode.AUTH_ERROR,
                    "System authentication error. Please contact your administrator.",
                    response.text[:500],
                )
            if response.status_code >= 400:
                raise MCPError(
                    ErrorCode.ERPNEXT_ERROR,
                    "An error occurred while communicating with the system.",
                    response.text[:500],
                )
            return response.json()

        raise MCPError(ErrorCode.RATE_LIMIT, "The system is busy. Please try again in a moment.")
