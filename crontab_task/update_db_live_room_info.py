import time
import logging
import asyncio
import datetime
import traceback
from utils.dao import redis_cache
from utils.biliapi import BiliApi
from utils.db_raw_query import AsyncMySQL
from config.log4 import lt_db_sync_logger as logging
from utils.reconstruction_model import objects, BiliUser

loop = asyncio.get_event_loop()


async def update_live_room_info():
    query = await AsyncMySQL.execute(
        "select real_room_id from biliuser where room_info_update_time >= %s",
        (datetime.datetime.now() - datetime.timedelta(days=15))
    )
    new_updated_room = [row[0] for row in query]
    if not new_updated_room:
        new_updated_room = [0]

    rooms_with_raffle = await AsyncMySQL.execute(
        (
            "select distinct room_id, count(id) "
            "from raffle "
            "where room_id not in %s "
            "group by room_id order by 2 desc;"
        ), (new_updated_room,)
    )
    rooms_with_guard = await AsyncMySQL.execute(
        (
            "select distinct room_id, count(id) "
            "from guard "
            "where room_id not in %s "
            "group by room_id order by 2 desc;"
        ), (new_updated_room,)
    )
    raffle_room_id = [r[0] for r in rooms_with_raffle]
    guard_room_id = [r[0] for r in rooms_with_guard]
    search_list = list(set(raffle_room_id[:600] + guard_room_id[:600]))
    total_search_count = len(search_list)

    logging.info(f"Start searching, total count: {total_search_count}, new_updated_room: {len(new_updated_room)}")

    for i, room_id in enumerate(search_list):
        i += 1

        flag, data = await BiliApi.get_live_room_info_by_room_id(room_id=room_id)
        if not flag:
            logging.error(f"Cannot get_live_room info! e: {data}")
            continue

        uid = data["uid"]
        real_room_id = data["room_id"]
        short_room_id = data["short_id"] or None
        if (
            short_room_id in (0, "", "0", None, "null")
            or (isinstance(short_room_id, int) and short_room_id < 0)
        ):
            short_room_id = real_room_id

        title = data["title"]
        create_at = datetime.datetime.now() - datetime.timedelta(days=365 * 5)
        attention = data["attention"]
        room_info_update_time = datetime.datetime.now()

        flag, user_info = await BiliApi.get_user_info(uid)
        if not flag:
            logging.error(f"Cannot get user_info! uid: {uid}, real_room_id: {real_room_id}")
            continue

        name = user_info["name"]
        face = user_info["face"]
        user_info_update_time = datetime.datetime.now()

        flag, guard_count = await BiliApi.get_master_guard_count(room_id=real_room_id, uid=uid)
        if not flag:
            logging.error(f"Cannot get master guard count! {name} room id -> {room_id}, msg: {guard_count}")
            guard_count = 0

        try:
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
        except Exception as e:
            logging.error(
                f"Update Failed! {i}/{total_search_count} -> "
                f"{name}(uid: {uid}), room_id: {real_room_id}, short {short_room_id}, "
                f"attention: {attention}, guard: {guard_count}, e: {e}"
            )
        else:
            logging.info(
                f"Update success {i}/{total_search_count} -> "
                f"{name}(uid: {uid}): room_id: {real_room_id}, short: {short_room_id}, "
                f"attention: {attention}, guard: {guard_count}, obj: {obj.id}"
            )


async def main():
    start_time = time.time()
    logging.info("Now updating live room info in database.")

    execute_key = "CRON_UPDATE_LIVE_ROOM_INFO"
    finished = await redis_cache.set_if_not_exists(execute_key, 1, timeout=60*55)
    if not finished:
        logging.error(f"FIX_DATA running! Now exit...")
        return

    await objects.connect()
    try:
        await update_live_room_info()
    except Exception as e:
        logging.info(f"FIX_DATA Error: {e}\n{traceback.format_exc()}")

    await objects.close()
    await redis_cache.delete(execute_key)
    await redis_cache.close()

    cost = time.time() - start_time
    logging.info(f"Update live room info execute finished, cost: {cost/60:.3f} min.\n\n")


loop.run_until_complete(main())
