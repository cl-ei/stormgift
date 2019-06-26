import asyncio
import datetime
from utils.biliapi import BiliApi
from utils.model import GiftRec, LiveRoomInfo, objects

BiliApi.USE_ASYNC_REQUEST_METHOD = True
TASK_START_HOUR = 2
TASK_SLEEP_HOUR = 16


async def search_short_number():
    print("Get room id list from db...")

    condition = GiftRec.created_time >= datetime.datetime.now() - datetime.timedelta(days=60)
    room_id_list = await objects.execute(GiftRec.select(GiftRec.room_id).where(condition).distinct())
    room_id_list = {r.room_id for r in room_id_list}

    condition = LiveRoomInfo.update_time > datetime.datetime.now() - datetime.timedelta(days=2)
    updated_live_room_id_list = await objects.execute(
        LiveRoomInfo.select(LiveRoomInfo.real_room_id).where(condition).distinct()
    )
    updated_live_room_id_list = {r.real_room_id for r in updated_live_room_id_list}

    final_list = room_id_list - updated_live_room_id_list
    print(f"Final list: {len(final_list)}")

    for room_id in final_list:
        now_hour = datetime.datetime.now().hour
        if not TASK_START_HOUR < now_hour < TASK_SLEEP_HOUR:
            print("Enter sleep mode.")
            return

        live_room_info = {}

        req_url = F"https://api.live.bilibili.com/AppRoom/index?room_id={room_id}&platform=android"
        flag, data = await BiliApi.get(req_url, timeout=10, check_error_code=True)
        if flag and data["code"] in (0, "0"):
            short_room_id = data["data"]["show_room_id"]
            real_room_id = data["data"]["room_id"]
            user_id = data["data"]["mid"]

            live_room_info["short_room_id"] = short_room_id
            live_room_info["real_room_id"] = real_room_id
            live_room_info["title"] = ""  # data["data"]["title"].encode("utf-8")
            live_room_info["user_id"] = user_id
            live_room_info["create_at"] = data["data"]["create_at"]
            live_room_info["attention"] = data["data"]["attention"]

            req_url = f"https://api.live.bilibili.com/guard/topList?roomid={real_room_id}&page=1&ruid={user_id}"
            flag, data = await BiliApi.get(req_url, timeout=10, check_error_code=True)
            if not flag:
                print(f"Error! e: {data}")
                continue

            live_room_info["guard_count"] = data["data"]["info"]["num"]
            print(f"{live_room_info}")

            flag, r = await LiveRoomInfo.update_live_room(**live_room_info)
            print(
                f"Update {'success' if flag else 'Failed'}! room_id: "
                f"{live_room_info['short_room_id']}->{live_room_info['real_room_id']}, r: {r}"
            )
        await asyncio.sleep(20)


async def main():
    await objects.connect()

    while True:
        now_hour = datetime.datetime.now().hour
        if TASK_START_HOUR < now_hour < TASK_SLEEP_HOUR:
            await search_short_number()

        print("Now sleep...")
        await asyncio.sleep(60*10)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
