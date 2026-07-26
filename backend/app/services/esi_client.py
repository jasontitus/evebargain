import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Limits how many ESI requests are in flight at once. A full Jita order pull is
# ~275 pages fetched concurrently, so without this the app would open a socket
# per page.
_request_semaphore = asyncio.Semaphore(settings.esi_max_concurrency)


class ESIClient:
    """Async HTTP client for EVE Swagger Interface (ESI) API."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        # path+params -> (etag, parsed_json). ESI serves market pages from a
        # ~300s cache, so a conditional request inside that window comes back
        # 304 with no body: cheaper for CCP and much faster for us.
        self._etags: dict[str, tuple[str, object]] = {}

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.esi_base_url,
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                    # CCP asks third-party apps to identify themselves so they
                    # can contact the author about a misbehaving client rather
                    # than blocking it outright.
                    "User-Agent": settings.esi_user_agent,
                },
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _cache_key(path: str, params: dict | None) -> str:
        if not params:
            return path
        return path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))

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

    async def post(
        self,
        path: str,
        json: object,
        token: str | None = None,
    ) -> httpx.Response:
        """POST to ESI. Used for bulk lookups like /universe/names/, which
        resolve many IDs in one request instead of one GET each."""
        client = await self.get_client()
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with _request_semaphore:
            response = await client.post(path, json=json, headers=headers)

            if response.status_code == 420:
                reset = int(response.headers.get("X-Esi-Error-Limit-Reset", 60))
                logger.warning(f"ESI error limited, waiting {reset}s")
                await asyncio.sleep(reset)
                response = await client.post(path, json=json, headers=headers)

            response.raise_for_status()
            return response

    async def get_json(
        self,
        path: str,
        token: str | None = None,
        params: dict | None = None,
    ) -> tuple[object, httpx.Response]:
        """GET and decode JSON, using a stored ETag to ask for only changes.

        On a 304 the server sends no body, so the previously decoded value is
        returned instead. Authenticated requests are not cached -- the response
        varies per character and the payloads are small.
        """
        if token:
            response = await self.get(path, token=token, params=params)
            return response.json(), response

        key = self._cache_key(path, params)
        cached = self._etags.get(key)

        client = await self.get_client()
        headers = {"If-None-Match": cached[0]} if cached else {}

        async with _request_semaphore:
            response = await client.get(path, params=params, headers=headers)

            remaining = response.headers.get("X-Esi-Error-Limit-Remain")
            if remaining and int(remaining) < 20:
                logger.warning(f"ESI error limit low: {remaining} remaining")

            if response.status_code == 420:
                reset = int(response.headers.get("X-Esi-Error-Limit-Reset", 60))
                logger.warning(f"ESI error limited, waiting {reset}s")
                await asyncio.sleep(reset)
                response = await client.get(path, params=params, headers=headers)

            if response.status_code == 304 and cached:
                return cached[1], response

            response.raise_for_status()
            data = response.json()

            etag = response.headers.get("ETag")
            if etag:
                self._etags[key] = (etag, data)

            return data, response

    async def get_paginated(
        self,
        path: str,
        token: str | None = None,
        params: dict | None = None,
        on_progress: "Callable[[int, int], Awaitable[None]] | None" = None,
    ) -> list:
        """Fetch all pages of a paginated ESI endpoint.

        on_progress, if given, is awaited with (completed, total) as pages land
        so callers can report progress on the long multi-hundred-page pulls.
        """
        if params is None:
            params = {}

        # Fetch first page to get total page count
        params["page"] = 1
        first_data, first_response = await self.get_json(path, token=token, params=params)
        total_pages = int(first_response.headers.get("X-Pages", 1))
        results = list(first_data)

        if on_progress:
            await on_progress(1, total_pages)

        if total_pages <= 1:
            return results

        # Emit at most ~20 updates over the whole pull. One message per page
        # would put 274 sends on the socket for a single Jita fetch.
        step = max(1, total_pages // 20)
        completed = 1

        async def fetch_page(page: int) -> list:
            nonlocal completed
            page_params = {**params, "page": page}
            data, _ = await self.get_json(path, token=token, params=page_params)
            completed += 1
            if on_progress and (completed % step == 0 or completed == total_pages):
                await on_progress(completed, total_pages)
            return data

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
