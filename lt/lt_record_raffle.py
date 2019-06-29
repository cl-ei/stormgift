import time
import asyncio
import datetime
import traceback
from random import random
from utils.highlevel_api import ReqFreLimitApi
from config.log4 import lt_raffle_id_getter_logger as logging
from utils.dao import DanmakuMessageQ
from utils.model import objects, RaffleRec


class Executor(object):
    async def record_raffle_info(self, msg):
        danmaku, args, kwargs = msg
        created_time = args[0]
        msg_from_room_id = args[1]
        created_time = datetime.datetime.now() - datetime.timedelta(seconds=(time.time() - created_time))

        if danmaku["cmd"] == "RAFFLE_END":
            data = danmaku["data"]
            user_name = data["uname"]
            uid = await ReqFreLimitApi.get_uid_by_name(user_name)
            create_param = {
                "cmd": "RAFFLE_END",
                "room_id": msg_from_room_id,
                "raffle_id": int(data["raffleId"]),
                "gift_name": data["giftName"],
                "count": data.get("win", {}).get("giftNum", -1),
                "msg": data["mobileTips"],
                "user_id": uid,
                "user_name": user_name,
                "user_face": data.get("win", {}).get("face", -1),
                "created_time": created_time,
            }
            obj = await RaffleRec.create(**create_param)
            logging.info(f"RaffleRec cmd: {danmaku['cmd']}, save result: id: {obj.id}, obj: {obj}")

        elif danmaku["cmd"] == "TV_END":
            data = danmaku["data"]
            user_name = data["uname"]
            uid = await ReqFreLimitApi.get_uid_by_name(user_name)
            create_param = {
                "cmd": "TV_END",
                "room_id": msg_from_room_id,
                "raffle_id": int(data["raffleId"]),
                "gift_name": data["giftName"],
                "count": data.get("win", {}).get("giftNum", -1),
                "msg": data["mobileTips"],
                "user_id": uid,
                "user_name": user_name,
                "user_face": data.get("win", {}).get("face", -1),
                "created_time": created_time,
            }
            obj = await RaffleRec.create(**create_param)
            logging.info(f"RaffleRec cmd: {danmaku['cmd']}, save result: id: {obj.id}, obj: {obj}")

        else:
            return f"RAFFLE_RECORD received error cmd `{danmaku['cmd']}`!"

    async def run(self):
        monitor_commands = ['RAFFLE_END', 'TV_END']
        while True:
            msg = await DanmakuMessageQ.get(*monitor_commands, timeout=50)
            if msg is None:
                continue

            start_time = time.time()
            task_id = str(random())[2:]
            logging.info(f"RAFFLE_RECORD Task[{task_id}] start...")

            try:
                r = await self.record_raffle_info(msg)
            except Exception as e:
                logging.error(f"RAFFLE_RECORD Task[{task_id}] error: {e}, msg: `{msg}`, {traceback.format_exc()}")
            else:
                cost_time = time.time() - start_time
                logging.info(f"RAFFLE_RECORD Task[{task_id}] success, r: {r}, cost time: {cost_time:.3f}")


async def main():
    logging.info("Starting Raffle record process...")

    await objects.connect()

    try:
        executor = Executor()
        await executor.run()
    except Exception as e:
        logging.error(f"Raffle record process shutdown! e: {e}, {traceback.format_exc()}")
    finally:
        await objects.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
