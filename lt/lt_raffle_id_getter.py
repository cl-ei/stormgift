import time
import asyncio
import datetime
import traceback
from random import random
from utils.biliapi import BiliApi
from config.log4 import lt_raffle_id_getter_logger as logging
from config import LT_ACCEPTOR_HOST, LT_ACCEPTOR_PORT
from utils.dao import DanmakuMessageQ, RaffleMessageQ
from utils.model import objects, GiftRec


class Executor(object):
    def __init__(self):
        self.cookie_file = "data/valid_cookies.txt"
        self.post_prize_url = f"http://{LT_ACCEPTOR_HOST}:{LT_ACCEPTOR_PORT}"

        self.__posted_keys = []

    def load_a_cookie(self):
        try:
            with open(self.cookie_file, "r") as f:
                cookies = [c.strip() for c in f.readlines()]
            return cookies[0]
        except:
            return ""

    @staticmethod
    async def proc_single_gift_of_guard(room_id, gift_info):
        gift_id = gift_info.get('id', 0)

        key = F"G${room_id}${gift_id}"
        created_time = time.time()
        raffle_msg = (key, created_time)
        await RaffleMessageQ.put(raffle_msg)

        privilege_type = gift_info["privilege_type"]
        if privilege_type == 3:
            gift_name = "舰长"
        elif privilege_type == 2:
            gift_name = "提督"
        elif privilege_type == 1:
            gift_name = "总督"
        else:
            gift_name = "guard_%s" % privilege_type

        expire_time = gift_info["created_time"] + datetime.timedelta(seconds=gift_info["time"])
        sender = gift_info["sender"]

        gift_rec_params = {
            "room_id": room_id,
            "gift_id": gift_id,
            "gift_name": gift_name,
            "gift_type": "G%s" % privilege_type,
            "sender_type": None,
            "created_time": gift_info["created_time"],
            "status": gift_info["status"],
            "expire_time": expire_time,
            "uid": sender["uid"],
            "name": sender["uname"],
            "face": sender["face"],
        }
        await GiftRec.create(**gift_rec_params)

    async def force_get_uid_by_name(self, user_name):
        cookie = self.load_a_cookie()
        if not cookie:
            logging.error("Cannot load cookie!")
            return None

        for retry_time in range(3):
            r, uid = await BiliApi.get_user_id_by_search_way(user_name)
            if r and isinstance(uid, (int, float)) and uid > 0:
                return uid

            # Try other way
            await BiliApi.add_admin(user_name, cookie)

            flag, admin_list = await BiliApi.get_admin_list(cookie)
            if not flag:
                continue

            uid = None
            for admin in admin_list:
                if admin.get("uname") == user_name:
                    uid = admin.get("uid")
                    break
            if isinstance(uid, (int, float)) and uid > 0:
                await BiliApi.remove_admin(uid, cookie)
                return uid
        return None

    async def proc_tv_gifts_by_single_user(self, user_name, gift_list):
        uid = await self.force_get_uid_by_name(user_name)

        for info in gift_list:
            info["uid"] = uid
            room_id = info["room_id"]
            gift_id = info["gift_id"]

            raffle_msg = (f"T${room_id}${gift_id}", time.time())
            await RaffleMessageQ.put(raffle_msg)

            expire_time = info["created_time"] + datetime.timedelta(seconds=info["time"])
            gift_rec_params = {
                "room_id": room_id,
                "gift_id": gift_id,
                "gift_name": info["gift_name"],
                "gift_type": info["gift_type"],
                "sender_type": info["sender_type"],
                "created_time": info["created_time"],
                "status": info["status"],
                "expire_time": expire_time,
                "uid": uid,
                "name": info["name"],
                "face": info["face"],
            }
            await GiftRec.create(**gift_rec_params)

    async def proc_single_msg(self, msg):
        danmaku, args, kwargs = msg
        created_time = args[0]
        msg_from_room_id = args[1]

        if time.time() - created_time > 30:
            return "EXPIRED DANMAKU !"

        if danmaku["cmd"] == "GUARD_MSG":
            key_type = "G"
            room_id = danmaku['roomid']

        elif danmaku["cmd"] == "NOTICE_MSG":
            key_type = "T"
            room_id = danmaku['real_roomid']

        elif danmaku["cmd"] == "GUARD_BUY":
            key_type = "G"
            room_id = msg_from_room_id
        else:
            return f"Error cmd `{danmaku['cmd']}`!"

        created_time = datetime.datetime.now()

        room_id = await BiliApi.force_get_real_room_id(room_id)
        if key_type == "G":
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
            for info in gift_info_list:
                user_name = info.get("from_user").get("uname")
                i = {
                    "name": user_name,
                    "face": info.get("from_user").get("face"),
                    "room_id": room_id,
                    "gift_id": info.get("raffleId", 0),
                    "gift_name": info.get("title"),
                    "gift_type": info.get("type"),
                    "sender_type": info.get("sender_type"),
                    "created_time": created_time,
                    "status": info.get("status"),
                    "time": info.get("time"),
                }
                result.setdefault(user_name, []).append(i)

            for user_name, gift_list in result.items():
                await self.proc_tv_gifts_by_single_user(user_name, gift_list)

    async def run(self):
        monitor_commands = ["GUARD_MSG", "NOTICE_MSG", "GUARD_BUY"]
        while True:
            msg = await DanmakuMessageQ.get(*monitor_commands, timeout=50)
            if msg is None:
                continue

            start_time = time.time()
            task_id = str(random())[2:]
            logging.info(f"RAFFLE Task[{task_id}] start...")

            try:
                r = await self.proc_single_msg(msg)
            except Exception as e:
                logging.error(f"RAFFLE Task[{task_id}] error: {e}, {traceback.format_exc()}")
            else:
                cost_time = time.time() - start_time
                logging.info(f"RAFFLE Task[{task_id}] success, r: {r}, cost time: {cost_time:.3f}")


async def main():
    logging.info("Starting raffle id getter process...")

    await objects.connect()

    try:
        executor = Executor()
        await executor.run()
    except Exception as e:
        logging.error(f"Raffle id getter process shutdown! e: {e}, {traceback.format_exc()}")
    finally:
        await objects.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
