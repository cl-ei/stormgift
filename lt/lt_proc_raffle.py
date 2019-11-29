import time
import json
import asyncio
import datetime
import traceback
from random import random
from config import config
from config.g import *
from utils.biliapi import BiliApi
from utils.cq import CQClient, qq, async_zy
from utils.dao import redis_cache, RaffleToCQPushList, BiliToQQBindInfo, DelayAcceptGiftsMQ
from utils.mq import mq_raffle_to_acceptor, mq_source_to_raffle, mq_raffle_broadcast
from utils.highlevel_api import ReqFreLimitApi
from config.log4 import lt_raffle_id_getter_logger as logging
from utils.reconstruction_model import Guard, Raffle, objects, BiliUser

GIFT_TYPE_TO_NAME = {
    "small_tv": "小电视飞船抽奖",
    "GIFT_30035": "任意门抽奖",
    "GIFT_30207": "幻乐之声抽奖",
    "GIFT_20003": "摩天大楼抽奖",
    "GIFT_30266": "金腰带抽奖",
}
api_root = config["ml_bot"]["api_root"]
access_token = config["ml_bot"]["access_token"]
ml_qq = CQClient(api_root=api_root, access_token=access_token)


class Worker(object):
    def __init__(self, index):
        self.index = index

    @staticmethod
    async def tracking(danmaku, created_time, msg_from_room_id):
        if msg_from_room_id == 2516117:
            return

        info = danmaku["info"]
        uid = info[2][0]
        if uid != 65568410:
            return

        msg = str(info[1])
        user_name = info[2][1]
        is_admin = info[2][2]
        ul = info[4][0]
        d = info[3]
        dl = d[0] if d else "-"
        deco = d[1] if d else "undefined"

        qq_msg = f"{msg_from_room_id}: {'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}"
        logging.info(qq_msg)
        await qq.send_private_msg(user_id=80873436, message=qq_msg)

    @staticmethod
    async def record_raffle_info(danmaku, created_time, msg_from_room_id):
        created_time = datetime.datetime.now() - datetime.timedelta(seconds=(time.time() - created_time))

        cmd = danmaku["cmd"]
        if cmd in ("RAFFLE_END", "TV_END"):
            data = danmaku["data"]
            winner_name = data["uname"]
            winner_uid = await ReqFreLimitApi.get_uid_by_name(winner_name)
            winner_face = data["win"]["face"]

            raffle_id = int(data["raffleId"])
            gift_type = data["type"]
            sender_name = data["from"]
            sender_face = data["fromFace"]

            prize_gift_name = data["giftName"]
            prize_count = int(data["win"]["giftNum"])

            raffle_obj = await Raffle.get_by_id(raffle_id)
            if not raffle_obj:
                sender_uid = await ReqFreLimitApi.get_uid_by_name(sender_name)
                gift_gen_time = created_time - datetime.timedelta(seconds=180)
                gift_name = GIFT_TYPE_TO_NAME.get(gift_type, "-")
                raffle_create_param = {
                    "raffle_id": raffle_id,
                    "room_id": msg_from_room_id,
                    "gift_name": gift_name,
                    "gift_type": gift_type,
                    "sender_uid": sender_uid,
                    "sender_name": sender_name,
                    "sender_face": sender_face,
                    "created_time": gift_gen_time,
                    "expire_time": created_time,
                }
                raffle_obj = await Raffle.record_raffle_before_result(**raffle_create_param)

            update_param = {
                "prize_gift_name": prize_gift_name,
                "prize_count": prize_count,
                "winner_uid": winner_uid,
                "winner_name": winner_name,
                "winner_face": winner_face,
                "danmaku_json_str": json.dumps(danmaku),
            }
            await Raffle.update_raffle_result(raffle_obj, **update_param)
            log_msg = f"Raffle saved! cmd: {cmd}, save result: id: {raffle_obj.id}. "

            qq_1 = await RaffleToCQPushList.get(bili_uid=winner_uid)
            if qq_1:
                message = f"恭喜{winner_name}[{winner_uid}]中了{prize_gift_name}！\n[CQ:at,qq={qq_1}]"
                r = await ml_qq.send_group_msg(group_id=981983464, message=message)
                log_msg += f"__ML NOTICE__ r: {r}"

            qq_2 = await BiliToQQBindInfo.get_by_bili(bili=winner_uid)
            if qq_2:
                flag, info = await BiliApi.get_live_room_info_by_room_id(room_id=msg_from_room_id)
                if flag:
                    room_id = info.get("short_id", msg_from_room_id) or msg_from_room_id
                else:
                    room_id = msg_from_room_id
                message = (
                    f"恭喜{winner_name}({winner_uid})[CQ:at,qq={qq_2}]"
                    f"获得了{sender_name}提供的{prize_gift_name}!\n"
                    f"https://live.bilibili.com/{room_id}"
                )
                await async_zy.send_group_msg(group_id=QQ_GROUP_STAR_LIGHT, message=message)
            logging.info(log_msg)

        elif cmd == "ANCHOR_LOT_AWARD":
            objs = await objects.execute(BiliUser.select().where(BiliUser.real_room_id == msg_from_room_id))
            if objs:
                sender = objs[0]
                sender_name = sender.name
                short_room_id = sender.short_room_id or msg_from_room_id
            else:
                flag, info = await BiliApi.get_live_room_info_by_room_id(room_id=msg_from_room_id)
                if not flag:
                    logging.error(f"ANCHOR_LOT_AWARD Cannot get live room info of {msg_from_room_id}, reason: {info}.")
                    return

                short_room_id = info["short_id"] or msg_from_room_id
                sender_uid = info["uid"]
                flag, info = await BiliApi.get_user_info(uid=sender_uid)
                if not flag:
                    logging.error(f"ANCHOR_LOT_AWARD Cannot get get_user_info. uid: {sender_uid}, reason: {info}.")
                    return

                sender_name = info["name"]
                sender_face = info["face"]
                sender = await BiliUser.get_or_update(uid=sender_uid, name=sender_name, face=sender_face)
                logging.info(f"ANCHOR_LOT_AWARD Sender info get from biliapi. {sender_name}({sender_uid})")

            data = danmaku["data"]
            prize_gift_name = data["award_name"]
            prize_count = data["award_num"]
            gift_name = "天选时刻"
            gift_type = "ANCHOR"
            raffle_id = data["id"]*10000

            for i, user in enumerate(data["award_users"]):
                inner_raffle_id = raffle_id + i
                winner_name = user["uname"]
                winner_uid = user["uid"]
                winner_face = user["face"]
                winner = await BiliUser.get_or_update(uid=winner_uid, name=winner_name, face=winner_face)
                r = await objects.create(
                    Raffle,
                    id=inner_raffle_id,
                    room_id=msg_from_room_id,
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
                logging.info(f"Raffle saved! cmd: {cmd}, save result: id: {r.id}. ")

                qq_2 = await BiliToQQBindInfo.get_by_bili(bili=winner_uid)
                if qq_2:
                    message = (
                        f"恭喜{winner_name}({winner_uid})[CQ:at,qq={qq_2}]"
                        f"在天选时刻抽奖中了{prize_gift_name}!\n"
                        f"https://live.bilibili.com/{short_room_id}"
                    )
                    await async_zy.send_group_msg(group_id=QQ_GROUP_STAR_LIGHT, message=message)

        else:
            return f"RAFFLE_RECORD received error cmd `{danmaku['cmd']}`!"

    @staticmethod
    async def proc_single_gift_of_guard(room_id, gift_info):
        gift_id = gift_info.get('id', 0)
        key = F"G${room_id}${gift_id}"

        if not await redis_cache.set_if_not_exists(key, gift_info):
            return
        await mq_raffle_to_acceptor.put(key)

        privilege_type = gift_info["privilege_type"]
        if privilege_type == 3:
            gift_name = "舰长"
        elif privilege_type == 2:
            gift_name = "提督"
        elif privilege_type == 1:
            gift_name = "总督"
        else:
            gift_name = "guard_%s" % privilege_type

        await mq_raffle_broadcast.put(json.dumps({
            "real_room_id": room_id,
            "raffle_id": gift_id,
            "gift_name": gift_name,
            "raffle_type": "guard"
        }, ensure_ascii=False))

        expire_time = gift_info["created_time"] + datetime.timedelta(seconds=gift_info["time"])
        sender = gift_info["sender"]
        create_param = {
            "gift_id": gift_id,
            "room_id": room_id,
            "gift_name": gift_name,
            "sender_uid": sender["uid"],
            "sender_name": sender["uname"],
            "sender_face": sender["face"],
            "created_time": gift_info["created_time"],
            "expire_time": expire_time,
        }
        await Guard.create(**create_param)

    @staticmethod
    async def proc_tv_gifts_by_single_user(user_name, gift_list):
        uid = await ReqFreLimitApi.get_uid_by_name(user_name, wait_time=1)

        for info in gift_list:
            info["uid"] = uid

            create_param = {
                "raffle_id": info["gift_id"],
                "room_id": info["room_id"],
                "gift_name": info["gift_name"],
                "gift_type": info["gift_type"],
                "sender_uid": uid,
                "sender_name": info["name"],
                "sender_face": info["face"],
                "created_time": info["created_time"],
                "expire_time": info["created_time"] + datetime.timedelta(seconds=info["time"])
            }
            await Raffle.record_raffle_before_result(**create_param)

    async def proc_single_msg(self, msg):
        created_time = datetime.datetime.now()
        key_type, room_id, *danmakus = msg

        if key_type == "R" and danmakus:
            danmaku = danmakus[0]
            created_time = time.time()
            return await self.record_raffle_info(danmaku, created_time, room_id)

        elif key_type == "D":
            danmaku = danmakus[0]
            info = danmaku.get("info", {})
            msg = str(info[1])
            uid = info[2][0]
            user_name = info[2][1]
            is_admin = info[2][2]
            ul = info[4][0]
            d = info[3]
            dl = d[0] if d else "-"
            deco = d[1] if d else "undefined"
            message = f"{room_id} ->\n\n{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}"
            logging.info(message)
            await async_zy.send_private_msg(user_id=80873436, message=message)

        elif key_type == "G":
            flag, gift_info_list = await BiliApi.get_guard_raffle_id(room_id)
            if not flag:
                logging.error(f"Guard proc_single_room, room_id: {room_id}, e: {gift_info_list}")
                return

            for gift_info in gift_info_list:
                gift_info["created_time"] = created_time
                await self.proc_single_gift_of_guard(room_id, gift_info=gift_info)

        elif key_type == "T":
            flag, gift_info_list = await BiliApi.get_tv_raffle_id(room_id)
            if not flag:
                logging.error(f"TV proc_single_room, room_id: {room_id}, e: {gift_info_list}")
                return

            result = {}
            gift_type = "default"
            gift_name = "default"
            for info in gift_info_list:
                user_name = info.get("from_user").get("uname")
                gift_id = info.get("raffleId", 0)
                gift_type = info.get("type")
                gift_name = info.get("thank_text", "").split("赠送的", 1)[-1]
                time_accept = int(time.time() + 1 + info.get("time_wait"))

                i = {
                    "name": user_name,
                    "face": info.get("from_user").get("face"),
                    "room_id": room_id,
                    "gift_id": gift_id,
                    "gift_name": gift_name,
                    "gift_type": gift_type,
                    "sender_type": info.get("sender_type"),
                    "created_time": created_time,
                    "status": info.get("status"),
                    "time": info.get("time"),
                }
                result.setdefault(user_name, []).append(i)
                key = f"T${room_id}${gift_id}"
                if not await redis_cache.set_if_not_exists(key, info):
                    continue

                await DelayAcceptGiftsMQ.put(f"T${room_id}${gift_id}${gift_type}", accept_time=time_accept)
                await mq_raffle_broadcast.put(json.dumps({
                    "real_room_id": room_id,
                    "raffle_id": gift_id,
                    "gift_name": gift_name,
                    "raffle_type": "tv"
                }, ensure_ascii=False))

            await redis_cache.set(key=f"GIFT_TYPE_{gift_type}", value=gift_name)

            for user_name, gift_list in result.items():
                await self.proc_tv_gifts_by_single_user(user_name, gift_list)

        elif key_type == "P" and danmakus:
            danmaku = danmakus[0]
            raffle_id = danmaku["data"]["id"]
            key = f"P${room_id}${raffle_id}"
            info = {"room_id": room_id, "raffle_id": raffle_id}
            if await redis_cache.set_if_not_exists(key, info):
                await mq_raffle_to_acceptor.put(key)
                await mq_raffle_broadcast.put(json.dumps({
                    "real_room_id": room_id,
                    "raffle_id": raffle_id,
                    "gift_name": "PK",
                    "raffle_type": "pk"
                }, ensure_ascii=False))

        elif key_type == "S":
            flag, raffle_id = await BiliApi.get_storm_raffle_id(room_id=room_id)
            if not flag:
                logging.info(f"Error happened when get raffle id of storm gift: e: {raffle_id}")
                return

            key = f"S${room_id}${raffle_id}"
            info = {"room_id": room_id, "raffle_id": raffle_id}
            if await redis_cache.set_if_not_exists(key, info):
                # await mq_raffle_to_acceptor.put(key)
                await mq_raffle_broadcast.put(json.dumps({
                    "real_room_id": room_id,
                    "raffle_id": raffle_id,
                    "gift_name": "节奏风暴",
                    "raffle_type": "storm"
                }, ensure_ascii=False))

        elif key_type == "A":
            # require_type = data["require_type"]
            # 0: 无限制; 1: 关注主播; 2: 粉丝勋章; 3大航海； 4用户等级；5主站等级

            danmaku = danmakus[0]
            data = danmaku["data"]
            raffle_id = data["id"]
            key = f"A${room_id}${raffle_id}"
            if await redis_cache.set_if_not_exists(key, 1):
                logging.info(f"A-> {danmaku}")

                join_type = data["join_type"]
                if join_type == 0:  # 免费参与
                    await mq_raffle_to_acceptor.put(key)
                else:
                    award_name = data["award_name"]
                    gift_name = data["gift_name"]
                    gift_num = data["gift_num"]
                    gift_price = data["gift_price"]
                    message = (
                        f"join_type: {join_type} -> {award_name}, need: {gift_name}*{gift_num}({gift_price})\n\n "
                        f"dan: {danmaku}"
                    )
                    await async_zy.send_private_msg(user_id=80873436, message=message)

                await mq_raffle_broadcast.put(json.dumps({
                    "real_room_id": room_id,
                    "raffle_id": raffle_id,
                    "gift_name": "天选时刻",
                    "raffle_type": "anchor",
                }, ensure_ascii=False))

    async def run_forever(self):
        while True:
            msg = await mq_source_to_raffle.get()

            start_time = time.time()
            task_id = f"{int(str(random())[2:]):x}"

            try:
                r = await self.proc_single_msg(msg)
            except Exception as e:
                logging.error(f"RAFFLE Task {self.index}-[{task_id}] error: {e}, {traceback.format_exc()}")
                continue

            cost_time = time.time() - start_time
            if cost_time > 5:
                logging.info(f"RAFFLE Task {self.index}-[{task_id}] success, r: {r}, cost time: {cost_time:.3f}")


async def main():
    logging.info("-" * 80)
    logging.info("LT PROC_RAFFLE started!")
    logging.info("-" * 80)
    await objects.connect()

    worker_tasks = [asyncio.create_task(Worker(index).run_forever()) for index in range(4)]
    for task in worker_tasks:
        await task


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
