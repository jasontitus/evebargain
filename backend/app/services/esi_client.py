import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Semaphore to limit concurrent ESI requests
_request_semaphore = asyncio.Semaphore(20)


class ESIClient:
    """Async HTTP client for EVE Swagger Interface (ESI) API."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.esi_base_url,
                timeout=30.0,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get(
        self,
        path: str,
        token: str | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        """Make an authenticated or public GET request to ESI."""
        client = await self.get_client()
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with _request_semaphore:
            response = await client.get(path, params=params, headers=headers)

            # Log rate limit status
            remaining = response.headers.get("X-Esi-Error-Limit-Remain")
            if remaining and int(remaining) < 20:
                logger.warning(f"ESI error limit low: {remaining} remaining")

            if response.status_code == 420:
                # Error rate limited - wait and retry once
                reset = int(response.headers.get("X-Esi-Error-Limit-Reset", 60))
                logger.warning(f"ESI error limited, waiting {reset}s")
                await asyncio.sleep(reset)
                response = await client.get(path, params=params, headers=headers)

            response.raise_for_status()
            return response

    async def get_paginated(
        self,
        path: str,
        token: str | None = None,
        params: dict | None = None,
    ) -> list:
        """Fetch all pages of a paginated ESI endpoint."""
        if params is None:
            params = {}

        # Fetch first page to get total page count
        params["page"] = 1
        first_response = await self.get(path, token=token, params=params)
        total_pages = int(first_response.headers.get("X-Pages", 1))
        results = first_response.json()

        if total_pages <= 1:
            return results

        # Fetch remaining pages concurrently
        async def fetch_page(page: int) -> list:
            page_params = {**params, "page": page}
            resp = await self.get(path, token=token, params=page_params)
            return resp.json()

        tasks = [fetch_page(p) for p in range(2, total_pages + 1)]
        pages = await asyncio.gather(*tasks, return_exceptions=True)

        for page_data in pages:
            if isinstance(page_data, Exception):
                logger.error(f"Failed to fetch page: {page_data}")
                continue
            results.extend(page_data)

        return results


# Singleton instance
esi_client = ESIClient()
