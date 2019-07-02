import asyncio
import datetime
from utils.biliapi import BiliApi
import traceback
from utils.model import GiftRec, LiveRoomInfo, objects
from utils.reconstruction_model import BiliUser
from config.log4 import lt_valuable_live_room_scanner_logger as logging
from utils.db_raw_query import AsyncMySQL

BiliApi.USE_ASYNC_REQUEST_METHOD = True
TASK_START_HOUR = 2
TASK_SLEEP_HOUR = 18


async def search_short_number():
    logging.info("Get room id list from db...")
    query = await AsyncMySQL.execute(
        (
            "select distinct room_id, count(id) "
            "from raffle "
            "where room_id not in (select real_room_id from biliuser where room_info_update_time >= %s) "
            "group by room_id order by 2 desc;"
        ), (datetime.datetime.now() - datetime.timedelta(days=2))
    )
    room_id_list = [row[0] for row in query]

    for room_id in room_id_list:
        req_url = F"https://api.live.bilibili.com/AppRoom/index?room_id={room_id}&platform=android"
        flag, response = await BiliApi.get(req_url, timeout=10, check_error_code=True)
        if flag and response["code"] in (0, "0"):

            data = response["data"]
            uid = data["mid"]
            name = data["uname"]
            face = data["face"]
            user_info_update_time = datetime.datetime.now()
            short_room_id = data["show_room_id"]
            real_room_id = data["room_id"]
            title = data["title"]
            create_at = data["create_at"]
            attention = data["attention"]

            req_url = f"https://api.live.bilibili.com/guard/topList?roomid={real_room_id}&page=1&ruid={uid}"
            flag, guard_response = await BiliApi.get(req_url, timeout=10, check_error_code=True)
            if not flag:
                logging.error(f"Error! e: {guard_response}")
                continue
            guard_count = guard_response["data"]["info"]["num"]

            guard_count = guard_count
            room_info_update_time = datetime.datetime.now()

            obj = await BiliUser.full_create_or_update(
                uid=uid,
                name=name,
                face=face,
                user_info_update_time=user_info_update_time,
                short_room_id=short_room_id,
                real_room_id=real_room_id,
                title=title,
                create_at=create_at,
                attention=attention,
                guard_count=guard_count,
                room_info_update_time=room_info_update_time,
            )

            logging.info(
                f"Update success ! room_id: {real_room_id} -> {short_room_id}, {uid} -> {name},"
                f" attention: {attention}, guard: {guard_count}, obj: {obj.id}"
            )

        await asyncio.sleep(5)


async def main():
    await objects.connect()

    await search_short_number()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
