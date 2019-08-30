import time
import asyncio
import datetime
import traceback
from random import random
from utils.biliapi import BiliApi
from config.log4 import lt_raffle_id_getter_logger as logging
from utils.dao import DanmakuMessageQ, RaffleMessageQ, TVPrizeMessageQ, redis_cache
from utils.highlevel_api import ReqFreLimitApi
from utils.reconstruction_model import objects, Guard, Raffle


class Executor(object):

    @staticmethod
    async def proc_single_gift_of_guard(room_id, gift_info):
        gift_id = gift_info.get('id', 0)
        key = F"G${room_id}${gift_id}"

        if not await redis_cache.set_if_not_exists(key, gift_info):
            return

        await RaffleMessageQ.put((key, time.time()))

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
            room_id = info["room_id"]
            gift_id = info["gift_id"]

            key = f"T${room_id}${gift_id}"
            if not await redis_cache.set_if_not_exists(key, info):
                return

            await RaffleMessageQ.put((key, time.time()))

            expire_time = info["created_time"] + datetime.timedelta(seconds=info["time"])
            create_param = {
                "raffle_id": gift_id,
                "room_id": room_id,
                "gift_name": info["gift_name"],
                "gift_type": info["gift_type"],
                "sender_uid": uid,
                "sender_name": info["name"],
                "sender_face": info["face"],
                "created_time": info["created_time"],
                "expire_time": expire_time
            }
            await Raffle.record_raffle_before_result(**create_param)

    async def proc_single_msg(self, msg):
        danmaku, created_time, msg_from_room_id, *_ = msg

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

        elif danmaku["cmd"] == "PK_LOTTERY_START":
            key_type = "P"
            room_id = msg_from_room_id

        else:
            return f"Error cmd `{danmaku['cmd']}`!"

        created_time = datetime.datetime.now()
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

        elif key_type == "P":
            raffle_id = danmaku["data"]["id"]
            key = f"P${room_id}${raffle_id}"
            info = {"room_id": room_id, "raffle_id": raffle_id}
            if await redis_cache.set_if_not_exists(key, info):
                await RaffleMessageQ.put((key, time.time()))

    async def get_raffle_id_of_tv(self):
        while True:
            msg_from_room_id = await TVPrizeMessageQ.get(timeout=50)
            if msg_from_room_id is None:
                continue

            start_time = time.time()
            task_id = str(random())[2:]
            logging.info(f"RAFFLE Task[{task_id}] start...")

            try:
                danmaku = {"cmd": "NOTICE_MSG", "real_roomid": msg_from_room_id}
                created_time = time.time()

                r = await self.proc_single_msg((danmaku, created_time, msg_from_room_id))
            except Exception as e:
                logging.error(f"RAFFLE Task[{task_id}] error: {e}, {traceback.format_exc()}")
            else:
                cost_time = time.time() - start_time
                logging.info(f"RAFFLE Task[{task_id}] success, r: {r}, cost time: {cost_time:.3f}")

    async def get_raffle_id_of_others(self):
        monitor_commands = ["GUARD_MSG", "NOTICE_MSG", "GUARD_BUY", "PK_LOTTERY_START"]
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

    async def run(self):
        tasks = (
            self.get_raffle_id_of_tv(),
            self.get_raffle_id_of_others()
        )
        await asyncio.gather(*tasks)


async def main():
    logging.info("Starting raffle id getter process...")

    await objects.connect()

    executor = Executor()
    try:
        await executor.run()
    except Exception as e:
        logging.error(f"Raffle id getter process shutdown! e: {e}, {traceback.format_exc()}")
    finally:
        await objects.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
