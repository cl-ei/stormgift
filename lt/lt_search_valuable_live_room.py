import asyncio
from utils.biliapi import BiliApi
from utils.dao import ValuableLiveRoom

BiliApi.USE_ASYNC_REQUEST_METHOD = True


async def search_short_number():
    print("search_short_number...")
    for room_id in range(1, 999):
        await asyncio.sleep(2)

        req_url = F"https://api.live.bilibili.com/AppRoom/index?room_id={room_id}&platform=android"
        flag, data = await BiliApi.get(req_url, timeout=10, check_error_code=True)
        if flag:
            short_room_id = data["data"]["show_room_id"]
            real_room_id = data["data"]["room_id"]
            r = await ValuableLiveRoom.add((short_room_id, real_room_id))
            print(f"Live room add: {short_room_id}->{real_room_id} -> {r}")
        else:
            if "not exists" in data:
                continue
            else:
                print(f"Room id: {room_id}, msg: {data}")

