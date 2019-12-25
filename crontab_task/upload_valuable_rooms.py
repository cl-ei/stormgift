import logging
import asyncio
from utils.dao import ValuableLiveRoom
from utils.db_raw_query import AsyncMySQL
from config.log4 import lt_db_sync_logger as logging


async def main():
    query = await AsyncMySQL.execute(
        "select real_room_id from biliuser "
        "where guard_count > 0 or attention > 10000 or real_room_id != short_room_id "
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


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
