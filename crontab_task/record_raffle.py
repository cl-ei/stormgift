import time
import asyncio
import datetime
import traceback
from utils.biliapi import BiliApi
from utils.reconstruction_model import objects, Guard, Raffle, BiliUser
from config.log4 import crontab_task_logger as logging
from utils.dao import redis_cache, RedisGuard, RedisRaffle, RedisAnchor, gen_x_node_redis


async def sync_guard(redis):
    data = await RedisGuard.get_all(redis=redis)
    for d in data:
        raffle_id = d["gift_id"]
        await Guard.create(**d)
        await RedisGuard.delete(raffle_id, redis=redis)
        logging.info(f"Saved: G:{d['gift_id']} {d['sender_name']} -> {d['room_id']}")


async def sync_raffle(redis):
    raffles = await RedisRaffle.get_all(redis=redis)
    for raffle in raffles:
        raffle_id = raffle["raffle_id"]
        if "winner_uid" in raffle and "winner_name" in raffle:
            r = await Raffle.create(**raffle)
        else:
            r = await Raffle.record_raffle_before_result(**raffle)
        logging.info(f"Saved: T:{raffle['raffle_id']} {r.id}")
        await RedisRaffle.delete(raffle_id, redis=redis)


async def sync_anchor(redis):
    raffles = await RedisAnchor.get_all(redis=redis)
    for raffle in raffles:
        raffle_id = raffle["id"]
        room_id = raffle["room_id"]
        prize_gift_name = raffle["award_name"]
        prize_count = raffle["award_num"]
        gift_name = "天选时刻"
        gift_type = "ANCHOR"

        users = await objects.execute(BiliUser.select().where(BiliUser.real_room_id == room_id))
        if users:
            sender = users[0]
            sender_name = sender.name
        else:
            flag, info = await BiliApi.get_live_room_info_by_room_id(room_id=room_id)
            if not flag:
                logging.error(f"ANCHOR_LOT_AWARD Cannot get live room info of {room_id}, reason: {info}.")
                continue

            sender_uid = info["uid"]
            flag, info = await BiliApi.get_user_info(uid=sender_uid)
            if not flag:
                logging.error(f"ANCHOR_LOT_AWARD Cannot get get_user_info. uid: {sender_uid}, reason: {info}.")
                continue

            sender_name = info["name"]
            sender_face = info["face"]
            sender = await BiliUser.get_or_update(uid=sender_uid, name=sender_name, face=sender_face)
            logging.info(f"ANCHOR_LOT_AWARD Sender info get from biliapi. {sender_name}({sender_uid})")

        for i, user in enumerate(raffle["award_users"]):
            inner_raffle_id = raffle_id*10000 + i
            winner_name = user["uname"]
            winner_uid = user["uid"]
            winner_face = user["face"]
            winner = await BiliUser.get_or_update(uid=winner_uid, name=winner_name, face=winner_face)

            r = await objects.create(
                Raffle,
                id=inner_raffle_id,
                room_id=room_id,
                gift_name=gift_name,
                gift_type=gift_type,
                sender_obj_id=sender.id,
                sender_name=sender_name,
                winner_obj_id=winner.id,
                winner_name=winner_name,
                prize_gift_name=prize_gift_name,
                prize_count=prize_count,
                created_time=datetime.datetime.now() - datetime.timedelta(seconds=600),
                expire_time=datetime.datetime.now()
            )
            logging.info(f"Saved: Anchor:{raffle_id} {r.id}")

        await RedisAnchor.delete(raffle_id, redis=redis)


async def main():
    lock_key = "EXE_RECORD_RAFFLE"
    if not await redis_cache.set_if_not_exists(lock_key, value=1, timeout=60*3):
        logging.info("RECORD_RAFFLE Another proc is Running.")
        await redis_cache.close()
        return

    await objects.connect()
    x_node_redis = await gen_x_node_redis()

    try:
        await sync_guard(x_node_redis)
        await sync_raffle(x_node_redis)
        await sync_anchor(x_node_redis)
    except Exception as e:
        logging.error(f"{e}\n{traceback.format_exc()}")

    # tears down.
    await x_node_redis.close()
    await objects.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
