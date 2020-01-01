import time
import peewee
import asyncio
import datetime
import traceback
from config import g
from config import config
from utils.cq import async_zy
from utils.cq import CQClient
from utils.biliapi import BiliApi
from utils.dao import RaffleToCQPushList
from utils.highlevel_api import ReqFreLimitApi
from config.log4 import crontab_task_logger as logging
from utils.reconstruction_model import objects, Guard, Raffle, BiliUser
from utils.dao import redis_cache, RedisGuard, RedisRaffle, RedisAnchor, gen_x_node_redis

api_root = config["ml_bot"]["api_root"]
access_token = config["ml_bot"]["access_token"]
ml_qq = CQClient(api_root=api_root, access_token=access_token)


async def notice_qq(room_id, winner_uid, winner_name, prize_gift_name, sender_name):

    qq_1 = await RaffleToCQPushList.get(bili_uid=winner_uid)
    if qq_1:
        message = f"恭喜{winner_name}[{winner_uid}]中了{prize_gift_name}！\n[CQ:at,qq={qq_1}]"
        r = await ml_qq.send_group_msg(group_id=981983464, message=message)
        logging.info(f"__ML NOTICE__ r: {r}")

    if winner_uid in (g.BILI_UID_DD, g.BILI_UID_TZ, g.BILI_UID_CZ):
        message = (
            f"恭喜{winner_name}({winner_uid})[CQ:at,qq={g.QQ_NUMBER_DD}]"
            f"获得了{sender_name}提供的{prize_gift_name}!\n"
            f"https://live.bilibili.com/{room_id}"
        )
        await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message=message)


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
        cloud_get_uid = False
        if "winner_uid" in raffle and "winner_name" in raffle:
            uid = raffle["winner_uid"]
            name = raffle["winner_name"]
            if not uid:
                uid = await BiliUser.get_uid_by_name(name=name)
            if not uid:
                cloud_get_uid = True
                uid = await ReqFreLimitApi.get_uid_by_name(user_name=name)

            raffle["winner_uid"] = uid
            try:
                r = await Raffle.create(**raffle)
            except peewee.IntegrityError as e:
                if "Duplicate entry" in f"{e}":
                    pass
                raise e

            if uid:
                # notice
                await notice_qq(
                    room_id=raffle["room_id"],
                    winner_uid=uid,
                    winner_name=name,
                    prize_gift_name=raffle["prize_gift_name"],
                    sender_name=raffle["sender_name"]
                )
            logging.info(f"Saved: T:{raffle['raffle_id']} {r.id} Raffle Full. cloud_get_uid: {cloud_get_uid}")

        else:
            r = await Raffle.record_raffle_before_result(**raffle)
            logging.info(f"Saved: T:{raffle['raffle_id']} {r.id} Raffle Pre.")

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

            try:
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
            except peewee.IntegrityError as e:
                if "Duplicate entry" in f"{e}":
                    pass
                raise e

            # notice
            await notice_qq(
                room_id=room_id,
                winner_uid=winner_uid,
                winner_name=winner_name,
                prize_gift_name=prize_gift_name,
                sender_name=sender_name,
            )

        await RedisAnchor.delete(raffle_id, redis=redis)


async def main():
    start_time = time.time()

    lock_key = "EXE_RECORD_RAFFLE"
    if not await redis_cache.set_if_not_exists(lock_key, value=1, timeout=60*3):
        logging.info("RECORD_RAFFLE Another proc is Running. Now exit.")
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

    await redis_cache.delete(lock_key)
    await redis_cache.set(key="LT_RAFFLE_DB_UPDATE_TIME", value=time.time())
    await redis_cache.close()
    logging.info(f"RECORD_RAFFLE done! cost: {time.time() - start_time:.3f}.")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
