import time
import asyncio
from utils.biliapi import BiliApi
from utils.dao import MonitorLiveRooms
from utils.model import objects, MonitorWsClient
from config.log4 import lt_server_logger as logging
from utils.ws import get_ws_established_and_time_wait

MONITOR_COUNT = 20000


async def batch_get_live_room_ids(count) -> list:

    async def get_one_page(page_no):
        for _try_times in range(3):
            if _try_times != 0:
                logging.info(f"get one page Failed: page no {page_no}, failed times: {_try_times}")

            flag, data = await BiliApi.get_lived_room_id_by_page(page=page_no, page_size=page_size, timeout=30)
            await asyncio.sleep(1)
            if not flag:
                continue
            if isinstance(data, list):
                return data
        return []

    page_size = 1000
    pages = (count + page_size) // page_size
    result = []
    for page in range(pages):
        result.extend(await get_one_page(page))

    de_dup = set()
    return_data = []
    for room_id in result:
        if room_id not in de_dup:
            de_dup.add(room_id)
            return_data.append(room_id)
            if len(return_data) >= MONITOR_COUNT:
                return return_data
    return return_data


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
        return

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
    await objects.connect()
    await MonitorWsClient.record(__monitor_info)
    await objects.close()
    return r


async def main():
    start = time.time()
    await get_live_rooms_from_api()
    logging.info(f"LT Flush monitor live room done, cost: {time.time() - start:.3f}.\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
