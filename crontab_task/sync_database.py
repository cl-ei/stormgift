import time
import logging
import asyncio

from config.log4 import crontab_task_logger as logging
from utils.dao import ValuableLiveRoom
from utils.db_raw_query import AsyncMySQL

loop = asyncio.get_event_loop()


class SyncTool(object):

    @classmethod
    async def sync_valuable_live_room(cls):
        query = await AsyncMySQL.execute(
            "select real_room_id from biliuser "
            "where guard_count > 20 or attention > 10000 or real_room_id != short_room_id "
            "order by guard_count desc, attention desc ;"
        )
        room_id = {row[0] for row in query}

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
        await cls.sync_valuable_live_room()
        logging.info("Execute finished, cost: %s.\n\n" % (time.time() - start_time))


loop.run_until_complete(SyncTool.run())
