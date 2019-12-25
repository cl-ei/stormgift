import time
import asyncio
from utils.biliapi import BiliApi
from utils.dao import MonitorLiveRooms
from utils.model import MonitorWsClient
from config.log4 import lt_source_logger as logging
from utils.ws import get_ws_established_and_time_wait

MONITOR_COUNT = 20000


async def get_live_rooms_from_api():
    flag, total = await BiliApi.get_all_lived_room_count()
    if not flag:
        logging.error(f"Cannot get lived room count! msg: {total}")
        return

    flag, living_room_id_list = await BiliApi.get_lived_room_id_list(count=min(total, MONITOR_COUNT))
    if not flag:
        logging.error(f"Cannot get lived rooms. msg: {living_room_id_list}")
        return
    r = await MonitorLiveRooms.set(living_room_id_list)
    logging.info(f"MonitorLiveRooms set, r: {r}, api count: {len(living_room_id_list)}")

    established, time_wait = get_ws_established_and_time_wait()
    __monitor_info = {
        "api room cnt": len(living_room_id_list),
        "TCP ESTABLISHED": established,
        "TCP TIME_WAIT": time_wait,
    }
    await MonitorWsClient.record(__monitor_info)
    return r


async def main():
    start = time.time()
    await get_live_rooms_from_api()
    logging.info(f"LT Flush monitor live room done, cost: {time.time() - start:.3f}.")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
