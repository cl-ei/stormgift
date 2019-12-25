import time
import asyncio
from utils.biliapi import BiliApi
from utils.dao import MonitorLiveRooms
from utils.model import MonitorWsClient
from config.log4 import crontab_task_logger as logging
from utils.ws import get_ws_established_and_time_wait

MONITOR_COUNT = 20000


async def batch_get_live_room_ids(count) -> set:
    pages = (count + 500) // 500
    result = [[] for _ in range(pages)]

    async def get_one_page(page_no):
        for _try_times in range(3):
            if _try_times != 0:
                logging.info(f"get one page Failed: page no {page_no}, failed times: {_try_times}")

            flag, data = await BiliApi.get_lived_room_id_by_page(page=page_no, timeout=30)
            if not flag:
                await asyncio.sleep(1)
                continue

            result[page_no] = data
            return

    await asyncio.gather(*[
        get_one_page(page_number)
        for page_number in range(pages)
    ])

    living_rooms = set()
    for page_data in result:
        for room_id in page_data:
            living_rooms.add(room_id)
            if len(living_rooms) >= MONITOR_COUNT:
                return living_rooms
    return living_rooms


async def get_live_rooms_from_api():
    start = time.time()
    flag, total = await BiliApi.get_all_lived_room_count()
    if not flag:
        logging.error(f"Cannot get lived room count! msg: {total}")
        return

    target_count = min(total, MONITOR_COUNT)
    living_room_id_list = await batch_get_live_room_ids(count=target_count)
    api_cost = time.time() - start

    if abs(target_count - len(living_room_id_list)) > 1001:
        logging.error("从api获取的直播间数与目标差异过大，不予更新。")

    start = time.time()
    r = await MonitorLiveRooms.set(living_room_id_list)
    redis_cost = time.time() - start
    api_count = len(living_room_id_list)
    logging.info(f"MonitorLiveRooms set {api_count}, r: {r}, api cost: {api_cost:.3f}, redis_cost: {redis_cost:.3f}")

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
