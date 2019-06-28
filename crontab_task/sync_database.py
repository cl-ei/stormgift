import time
import logging
import asyncio
import aioredis

from config.log4 import crontab_task_logger as logging
from config import REDIS_CONFIG
from utils.model import LiveRoomInfo, objects
from utils.dao import ValuableLiveRoom

loop = asyncio.get_event_loop()


class SyncTool(object):

    @classmethod
    async def sync_valuable_live_room(cls):
        condition = (
            (LiveRoomInfo.guard_count > 5)
            & (
                (LiveRoomInfo.guard_count > 30)
                | (LiveRoomInfo.real_room_id != LiveRoomInfo.short_room_id)
                | (LiveRoomInfo.attention > 10000)
            )
        )
        select = (LiveRoomInfo.real_room_id, LiveRoomInfo.guard_count, LiveRoomInfo.attention)
        order_by = (LiveRoomInfo.guard_count.desc(), LiveRoomInfo.attention.desc())
        query = LiveRoomInfo.select(*select).where(condition).distinct().order_by(*order_by)
        r = await objects.execute(query)
        room_id = {e.real_room_id for e in r}
        logging.info(F"Valuable live rooms get from db success, count: {len(room_id)}")

        existed = set(await ValuableLiveRoom.get_all())
        need_add = room_id - existed
        need_del = existed - room_id

        r = await ValuableLiveRoom.add(*need_add)
        r2 = await ValuableLiveRoom.delete(*need_del)
        logging.info(f"Save to redis result: add: {r}, del: {r2}")

    @classmethod
    async def run(cls):
        start_time = time.time()
        await objects.connect()
        redis = await aioredis.create_connection(
            address='redis://%s:%s' % (REDIS_CONFIG["host"], REDIS_CONFIG["port"]),
            db=REDIS_CONFIG["db"],
            password=REDIS_CONFIG["password"],
            loop=loop
        )

        await cls.sync_valuable_live_room()

        redis.close()
        await redis.wait_closed()
        await objects.close()
        logging.info("Execute finished, cost: %s.\n\n" % (time.time() - start_time))


loop.run_until_complete(SyncTool.run())
