import re
import time
import asyncio
import datetime
from random import random
from utils.biliapi import BiliApi
from utils.ws import ReConnectingWsClient
from config import PRIZE_HANDLER_SERVE_ADDR
from config.log4 import acceptor_logger as logging

NON_SKIP_USER_ID = [
    20932326,  # DD
    39748080,  # LP
]


class Acceptor(object):
    def __init__(self):
        self.q = asyncio.Queue(maxsize=2000)
        self.cookie_file = "data/valid_cookies.txt"
        self.__black_list = {}

    async def add_task(self, key):
        await self.q.put(key)

    async def load_uid_and_cookie(self):
        """

        :return: [  # non_skip
            (uid, cookie),
            ...
        ],

        [       # normal

            (uid, cookie),
            ...
        ]
        """
        try:
            with open(self.cookie_file, "r") as f:
                cookies = [c.strip() for c in f.readlines()]
        except Exception as e:
            logging.exception(f"Cannot load cookie, e: {str(e)}.", exc_info=True)
            return []

        non_skip_cookies = []
        white_cookies = []

        now = time.time()
        t_12_hours = 3600*12
        for cookie in cookies:
            user_id = int(re.findall(r"DedeUserID=(\d+)", cookie)[0])
            block_time = self.__black_list.get(cookie)
            if isinstance(block_time, (int, float)) and now - block_time < t_12_hours:
                logging.info(f"User {user_id} in black list, skip it.")
                continue

            if user_id in NON_SKIP_USER_ID:
                non_skip_cookies.append((user_id, cookie))
            else:
                white_cookies.append((user_id, cookie))

        # GC
        if len(self.__black_list) > len(cookies):
            new_black_list = {}
            for cookie in self.__black_list:
                if cookie in cookies:
                    new_black_list[cookie] = self.__black_list[cookie]
            self.__black_list = new_black_list

        return non_skip_cookies, white_cookies

    async def add_to_black_list(self, cookie):
        self.__black_list[cookie] = time.time()
        user_ids = re.findall(r"DedeUserID=(\d+)", "".join(self.__black_list.keys()))
        logging.critical(f"Black list updated. current {len(user_ids)}: [{', '.join(user_ids)}].")

    async def accept_tv(self, i, user_id, room_id, gift_id, cookie):
        r, msg = await BiliApi.join_tv(room_id, gift_id, cookie)
        if r:
            logging.info(f"TV AC SUCCESS! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
        else:
            logging.critical(f"TV AC FAILED! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
            if "访问被拒绝" in msg:
                await self.add_to_black_list(cookie)

    async def accept_guard(self, i, user_id, room_id, gift_id, cookie):
        r, msg = await BiliApi.join_guard(room_id, gift_id, cookie)
        if r:
            logging.info(f"GUARD AC SUCCESS! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
        else:
            logging.critical(f"GUARD AC FAILED! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
            if "访问被拒绝" in msg:
                await self.add_to_black_list(cookie)

    async def accept_prize(self, key):
        if not isinstance(key, str):
            key = key.decode("utf-8")

        if key.startswith("_T"):
            process_fn = self.accept_tv
        elif key.startswith("NG"):
            process_fn = self.accept_guard
        else:
            logging.error(f"invalid key: {key}. skip it.")
            return

        try:
            room_id, gift_id = map(int, key[2:].split("$"))
        except Exception as e:
            logging.error(f"Bad prize key {key}, e: {str(e)}")
            return

        non_skip_cookies, white_cookies = await self.load_uid_and_cookie()

        display_index = -1
        for user_id, cookie in non_skip_cookies:
            display_index += 1
            await process_fn(display_index, user_id, room_id, gift_id, cookie)

        now_hour = datetime.datetime.now().hour
        busy_time = bool(now_hour < 2 or now_hour > 18)
        for user_id, cookie in white_cookies:
            display_index += 1

            if busy_time:
                if random() < 0.70:
                    logging.info(f"Too busy, user {user_id} skip.")
                    continue
                else:
                    await asyncio.sleep(random())

            await process_fn(display_index, user_id, room_id, gift_id, cookie)

    async def run_forever(self):
        while True:
            r = await self.q.get()
            await self.accept_prize(r)


async def main():
    a = Acceptor()

    async def on_message(key):
        logging.info(f"Acceptor: Prize message key received from server: {key}")
        await a.add_task(key)

    async def on_error(e, msg):
        logging.error(f"AC CATCH ERROR: {msg}. e: {e}")

    c = ReConnectingWsClient(
        uri="ws://%s:%s" % PRIZE_HANDLER_SERVE_ADDR,
        on_message=on_message,
        on_error=on_error,
    )
    await c.start()
    await a.run_forever()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
