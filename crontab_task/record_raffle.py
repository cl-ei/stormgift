import asyncio
from utils.dao import redis_cache, RedisGuard, RedisRaffle, RedisAnchor


async def sync_guard():
    r = RedisGuard.get_all()


async def main():
    await sync_guard()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
