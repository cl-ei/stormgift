import time
import os
import sys
import logging
import json
import aioredis
import datetime
import asyncio
from utils.biliapi import BiliApi


if sys.platform == "linux":
    LOG_PATH = "/home/wwwroot/log"
    with open("/home/wwwroot/stormgift/data/cookie.json") as f:
        COOKIE = json.load(f)["RAW_COOKIE_LIST"][0]
else:
    LOG_PATH = "./log"
    with open("data/cookie.json") as f:
        COOKIE = json.load(f)["RAW_COOKIE_LIST"][0]

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
            guard_lr_uid_list = await BiliApi.get_guard_live_room_id_list(COOKIE)
            for uid in guard_lr_uid_list:
                live_room_id = await BiliApi.get_live_room_id_by_uid(uid)
                print(live_room_id)
                r = await BiliApi.enter_room(live_room_id, COOKIE)
                print(r)
                await asyncio.sleep(20)
            logging.info("Execute finished, cost: %s.\n\n" % (time.time() - start_time))

            await asyncio.sleep(120)


loop = asyncio.get_event_loop()
loop.run_until_complete(Core.run())
