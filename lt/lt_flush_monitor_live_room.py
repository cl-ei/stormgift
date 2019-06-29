import asyncio
from config.log4 import lt_source_logger as logging
from utils.biliapi import BiliApi
from utils.ws import get_ws_established_and_time_wait
from utils.dao import ValuableLiveRoom, MonitorLiveRooms, InLotteryLiveRooms
from utils.model import MonitorWsClient

MONITOR_COUNT = 15000
VALUABLE_ROOM_COUNT_LIMIT = 3000


async def get_live_rooms_from_api():
    logging.info("Flush monitor live rooms...")

    flag, total = await BiliApi.get_all_lived_room_count()
    if not flag:
        logging.error(f"Cannot get lived room count! try times: {_}, msg: {total}")
        return

    await asyncio.sleep(1)
    flag, room_id_list = await BiliApi.get_lived_room_id_list(count=min(total, MONITOR_COUNT))
    if not flag:
        logging.error(f"Cannot get lived rooms. msg: {room_id_list}")
        return False

    in_lottery_live_rooms = await InLotteryLiveRooms().get_all()
    logging.info(f"Get in_lottery_live_rooms count: {len(in_lottery_live_rooms)}")
    room_id_list.extend(in_lottery_live_rooms)

    valuable_live_rooms = (await ValuableLiveRoom.get_all())[:VALUABLE_ROOM_COUNT_LIMIT]
    valuable_count = len(valuable_live_rooms)

    api_count = len(room_id_list)
    monitor_live_rooms = set(room_id_list + valuable_live_rooms)
    total_count = len(monitor_live_rooms)
    cache_hit_rate = 100 * (api_count + valuable_count - total_count) / valuable_count

    r = await MonitorLiveRooms.set(monitor_live_rooms)
    logging.info(
        f"monitor_live_rooms updated! r: {r} api count: {api_count}, valuable: {valuable_count}, "
        f"total: {total_count}, cache_hit_rate: {cache_hit_rate:.1f}%"
    )

    established, time_wait = get_ws_established_and_time_wait()
    __monitor_info = {
        "valuable room": valuable_count,
        "api room cnt": api_count,
        "target clients": total_count,
        "valuable hit rate": cache_hit_rate,
        "TCP ESTABLISHED": established,
        "TCP TIME_WAIT": time_wait,
    }
    await MonitorWsClient.record(__monitor_info)
    return True


async def flush_in_lottery_live_rooms():
    monitor_live_rooms = await MonitorLiveRooms.get()
    in_lottery = await InLotteryLiveRooms.get_all()
    target_monitor_live_rooms = monitor_live_rooms | in_lottery

    if target_monitor_live_rooms != monitor_live_rooms:
        await MonitorLiveRooms.set(target_monitor_live_rooms)
    logging.info(
        f"In lottery live room update! "
        f"count: {len(monitor_live_rooms)}, total: {len(target_monitor_live_rooms)}."
    )


async def main():
    logging.info("LT flush monitor live room proc starting ...")
    count = 0
    while True:
        if count % 5 == 0:
            logging.info("Flush monitor live room: Now get_live_rooms_from_api!")
            await get_live_rooms_from_api()

        else:
            logging.info("Flush monitor live room: Now flush_in_lottery_live_rooms!")
            await flush_in_lottery_live_rooms()

        await asyncio.sleep(60)
        count += 1
        count %= 99999999999


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
