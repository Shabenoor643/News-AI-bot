# FILE: src/utils/sleep.py | PURPOSE: Async sleep for rate limiting
import asyncio

async def sleep(ms: int) -> None:
    await asyncio.sleep(ms / 1000.0)
