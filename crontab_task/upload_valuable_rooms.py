import logging
import asyncio
from utils.dao import ValuableLiveRoom
from utils.db_raw_query import AsyncMySQL
from config.log4 import lt_db_sync_logger as logging


async def main():
    query = await AsyncMySQL.execute(
        f"select distinct real_room_id from biliuser "
        f"where short_room_id is not null and short_room_id != real_room_id ;"
    )
    forever_monitor_rooms = [r[0] for r in query]

    query = await AsyncMySQL.execute(
        "select real_room_id from biliuser "
        "where guard_count > 5 or attention > 10000 "
        "order by guard_count desc, attention desc ;"
    )
    recommend_room_id = [row[0] for row in query]

    valuable_rooms = []
    de_dup = set()
    for room_id in forever_monitor_rooms + recommend_room_id:
        if room_id in de_dup:
            continue
        de_dup.add(room_id)
        valuable_rooms.append(room_id)

    r = await ValuableLiveRoom.set(valuable_rooms)
    logging.info(F"Valuable live rooms get from db success, count: {len(valuable_rooms)}, r: {r}")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
