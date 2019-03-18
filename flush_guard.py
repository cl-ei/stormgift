import time
import os
import sys
import logging
import asyncio
from utils.biliapi import BiliApi


if sys.platform == "linux":
    LOG_PATH = "/home/wwwroot/log"
else:
    LOG_PATH = "./log"


logger_name = "flush_guard"
fh = logging.FileHandler(os.path.join(LOG_PATH, logger_name + ".log"), encoding="utf-8")
fh.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
logger = logging.getLogger(logger_name)
logger.setLevel(logging.DEBUG)
logger.addHandler(fh)
logger.addHandler(logging.StreamHandler(sys.stdout))
logging = logger


class Core(object):

    @classmethod
    async def run(cls):
        while True:
            logging.info("Running proc.")
            start_time = time.time()

            try:
                from data import COOKIE_DD as COOKIE
            except Exception as e:
                logging.error(f"Exception in load cookie: {e}.", exc_info=True)
                COOKIE = ""

            guard_lr_uid_list = await BiliApi.get_guard_live_room_id_list(COOKIE)
            execute_live_room = []
            for uid in guard_lr_uid_list:
                live_room_id = await BiliApi.get_live_room_id_by_uid(uid)
                flag, data = await BiliApi.enter_room(live_room_id, COOKIE)
                if not flag:
                    logging.error(f"Enter failed, room_id: {live_room_id}, r: {data}")
                else:
                    execute_live_room.append(live_room_id)
                await asyncio.sleep(20)

            cost_time = int(time.time() - start_time)
            sleep_time = max(0, 60*5 - cost_time)
            logging.info(f"Execute finished, cost: {cost_time}s, sleep: {sleep_time}s. "
                         f"execute_live_room: {execute_live_room}\n\n")
            await asyncio.sleep(sleep_time)


loop = asyncio.get_event_loop()
loop.run_until_complete(Core.run())
