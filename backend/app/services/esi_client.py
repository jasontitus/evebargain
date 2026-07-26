"""The single place this app talks to ESI, CCP's EVE Online web API.

Every outbound request goes through here, which is what makes it possible to
enforce good behaviour in one spot: identify ourselves, cap how many requests
run at once, avoid re-downloading unchanged data, and back off when told to.

THREE IDEAS WORTH UNDERSTANDING HERE
    1. Concurrency limiting (the semaphore, below). Fetching 275 pages at once
       would open 275 sockets and hammer CCP. A semaphore is a counter: each
       request takes a slot before starting and returns it when done, so only
       N run at a time and the rest queue.

    2. ETags. When ESI returns data it also returns an ETag -- a short
       fingerprint of that response. Send it back on the next request as
       `If-None-Match` and, if nothing changed, ESI replies "304 Not Modified"
       with no body at all. Cheaper for CCP, faster for us.

    3. Pagination. Large results arrive in pages, with the total count in an
       `X-Pages` header. `get_paginated` fetches page 1, learns how many there
       are, then requests the rest concurrently.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Limits how many ESI requests are in flight at once. A full Jita order pull is
# ~275 pages fetched concurrently, so without this the app would open a socket
# per page.
#
# Module-level, so it is shared by every caller in the process -- two different
# background jobs fetching at once still respect one combined limit.
_request_semaphore = asyncio.Semaphore(settings.esi_max_concurrency)


class ESIClient:
    """Async HTTP client for the EVE Swagger Interface (ESI) API.

    One instance is created at the bottom of this file and imported everywhere;
    it is not constructed per request, because reusing one client reuses its
    open connections instead of paying for a new TCP and TLS handshake each
    time.
    """

    def __init__(self):
        """Runs when the object is created. `self` is this particular instance."""
        self._client: httpx.AsyncClient | None = None
        # path+params -> (etag, parsed_json). ESI serves market pages from a
        # ~300s cache, so a conditional request inside that window comes back
        # 304 with no body: cheaper for CCP and much faster for us.
        self._etags: dict[str, tuple[str, object]] = {}

    async def get_client(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating it on first use.

        Created lazily rather than in __init__ because an httpx client wants to
        attach to the running event loop, which does not exist yet at import
        time.
        """
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
        """Shut the connections down cleanly. Called on app shutdown."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _cache_key(path: str, params: dict | None) -> str:
        """Build a stable string identifying one request, for the ETag store.

        The parameters are sorted so that {"page": 2, "order_type": "sell"} and
        {"order_type": "sell", "page": 2} produce the same key -- dictionaries
        preserve insertion order in Python, so without sorting these would look
        like two different requests and each would miss the cache.

        `@staticmethod` means it does not use `self`; it is grouped with the
        class for tidiness rather than needing any instance state.
        """
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

        # Waits here if `esi_max_concurrency` requests are already running,
        # then releases the slot automatically when the block exits -- even if
        # the request raises.
        async with _request_semaphore:
            response = await client.get(path, params=params, headers=headers)

            # Log rate limit status
            remaining = response.headers.get("X-Esi-Error-Limit-Remain")
            if remaining and int(remaining) < 20:
                logger.warning(f"ESI error limit low: {remaining} remaining")

            if response.status_code == 420:
                # ESI's real hard limit is on *errors*, not successful requests:
                # roughly 100 errors per 60 seconds, after which it answers 420
                # and tells you how long to wait. Sleeping and retrying once is
                # the polite response.
                reset = int(response.headers.get("X-Esi-Error-Limit-Reset", 60))
                logger.warning(f"ESI error limited, waiting {reset}s")
                await asyncio.sleep(reset)
                response = await client.get(path, params=params, headers=headers)

            # Turns a 4xx/5xx response into a raised exception, so callers can
            # use try/except rather than checking a status code every time.
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

        # Fetch page 1 first, because its X-Pages header is the only way to
        # learn how many pages there are.
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

        # Build a list of coroutines for pages 2..N, then run them all at once.
        # `asyncio.gather` waits for every one to finish; the semaphore is what
        # keeps "all at once" from meaning literally 274 simultaneous sockets.
        # return_exceptions=True makes a failed page come back as an exception
        # object instead of cancelling the whole batch -- one bad page should
        # not lose the other 273.
        tasks = [fetch_page(p) for p in range(2, total_pages + 1)]
        pages = await asyncio.gather(*tasks, return_exceptions=True)

        for page_data in pages:
            if isinstance(page_data, Exception):
                logger.error(f"Failed to fetch page: {page_data}")
                continue
            results.extend(page_data)

        return results


# The one shared instance. Because Python caches modules on first import,
# every `from app.services.esi_client import esi_client` gets this same object,
# so the ETag cache and connection pool are shared process-wide.
esi_client = ESIClient()
