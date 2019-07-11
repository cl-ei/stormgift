import time
import asyncio
import traceback
from random import random
from utils.biliapi import BiliApi
from config.log4 import console_logger as logging
from utils.highlevel_api import DBCookieOperator
from utils.dao import DanmakuMessageQ, redis_cache


class Executor(object):
    _update_time = 0
    _cached_cookies = None

    async def load_cookie(self):
        if time.time() - self._update_time > 10:
            self._cached_cookies = await DBCookieOperator.get_by_uid("DD")
            self._update_time = time.time()
        return self._cached_cookies

    async def accept_storm_gift(self, room_id, raffle_id):
        print(f"\n\nhttps://live.bilibili.com/{room_id}\n\n")

        cookie_obj = await self.load_cookie()
        await BiliApi.join_storm(room_id=room_id, raffle_id=raffle_id, cookie=cookie_obj.cookie)
        return True, ""

    async def get_raffle_id(self, msg):
        danmaku, created_time, msg_from_room_id, *_ = msg

        start_time = time.time()
        if start_time - created_time > 10:
            return "EXPIRED DANMAKU !"

        gift_name = danmaku["data"]["giftName"]
        if gift_name != "节奏风暴":
            return f"ERROR giftName: {gift_name}"

        flag, raffle_id = await BiliApi.get_storm_raffle_id(msg_from_room_id)
        if not flag:
            logging.error(f"Cannot get raffle id! msg: {raffle_id}")
            return

        flag, msg = await self.accept_storm_gift(msg_from_room_id, raffle_id)
        if not flag:
            logging.error(f"Cannot accept storm gift! msg: {msg}")

    async def run(self):
        while True:
            msg = await DanmakuMessageQ.get("SEND_GIFT", timeout=50)
            if msg is None:
                continue

            start_time = time.time()
            task_id = str(random())[2:]
            logging.info(f"STORM_GIFT ACCEPTOR Task[{task_id}] start...")

            try:
                r = await self.get_raffle_id(msg)
            except Exception as e:
                logging.error(f"STORM_GIFT ACCEPTOR Task[{task_id}] error: {e}, msg: `{msg}`, {traceback.format_exc()}")
                continue

            cost_time = time.time() - start_time
            logging.info(f"RAFFLE_RECORD Task[{task_id}] success, result: {r}, cost time: {cost_time:.3f}")


async def main():
    logging.info("Starting Storm acceptor process...")

    try:
        executor = Executor()
        await executor.run()
    except Exception as e:
        logging.error(f"Storm acceptor process shutdown! e: {e}, {traceback.format_exc()}")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
