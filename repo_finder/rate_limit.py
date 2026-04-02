import asyncio
import time

import httpx


async def retry_with_backoff(
    coro_factory,
    max_retries: int = 3,
    base_delay: float = 1.0,
):
    """Retry an async operation on transient failures (429, 5xx, timeouts).

    coro_factory is a callable that returns a new coroutine each time.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except httpx.HTTPStatusError as e:
            last_exc = e
            status = e.response.status_code
            if status == 429:
                retry_after = e.response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else base_delay * (2**attempt)
                await asyncio.sleep(delay)
            elif status >= 500:
                await asyncio.sleep(base_delay * (2**attempt))
            else:
                raise
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exc = e
            if attempt < max_retries:
                await asyncio.sleep(base_delay * (2**attempt))
    raise last_exc


async def safe_get(session: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """GET with retry on transient errors. Raises on 4xx (except 429)."""

    async def _do():
        resp = await session.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    return await retry_with_backoff(_do)


async def safe_get_or_none(
    session: httpx.AsyncClient, url: str, **kwargs
) -> httpx.Response | None:
    """GET that returns None on 404/403 instead of raising."""
    try:
        return await safe_get(session, url, **kwargs)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 403, 410, 451):
            return None
        raise
    except (httpx.TimeoutException, httpx.ConnectError):
        return None
