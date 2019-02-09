import re
import json
import asyncio
import time
from utils.ws import ReConnectingWsClient
from utils.biliapi import BiliApi
from config.log4 import acceptor_logger as logging
from config import config
PRIZE_HANDLER_SERVE_ADDR = tuple(config["PRIZE_HANDLER_SERVE_ADDR"])


class Acceptor(object):
    def __init__(self):
        self.q = asyncio.Queue(maxsize=2000)
        self.cookie_file = "data/cookie.json"
        self.__black_list = {}

    async def add_task(self, key):
        await self.q.put(key)

    async def load_cookie(self):
        try:
            with open(self.cookie_file, "r") as f:
                c = json.load(f)
            cookie_list = c["RAW_COOKIE_LIST"]
        except Exception as e:
            logging.error(f"Bad cookie, e: {str(e)}.", exc_info=True)
            return [], []

        blacklist = []
        for index in range(0, len(cookie_list)):
            cookie = cookie_list[index]
            bt = self.__black_list.get(cookie)
            if isinstance(bt, (int, float)) and int(time.time()) - bt < 3600*12:
                blacklist.append(index)

        if len(self.__black_list) > len(cookie_list):
            new_black_list = {}
            for cookie in self.__black_list:
                if cookie in cookie_list:
                    new_black_list[cookie] = self.__black_list[cookie]
            self.__black_list = new_black_list
            logging.critical("SELF BLACK LIST GC DONE!")
        return cookie_list, blacklist

    async def add_black_list(self, cookie):
        self.__black_list[cookie] = time.time()
        user_ids = ", ".join(re.findall(r"DedeUserID=(\d+)", "".join(self.__black_list.keys())))
        logging.critical(f"Black list updated. current {len(user_ids)}: [{user_ids}].")

    async def accept_tv(self, i, room_id, gift_id, cookie):
        uid_list = re.findall(r"DedeUserID=(\d+)", cookie)
        user_id = uid_list[0] if uid_list else "Unknown-uid"

        r, msg = await BiliApi.join_tv(room_id, gift_id, cookie)
        if r:
            logging.info(f"TV AC SUCCESS! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
        else:
            logging.critical(f"TV AC FAILED! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
            if "访问被拒绝" in msg:
                await self.add_black_list(cookie)

    async def accept_guard(self, i, room_id, gift_id, cookie):
        uid_list = re.findall(r"DedeUserID=(\d+)", cookie)
        user_id = uid_list[0] if uid_list else "Unknown-uid"

        r, msg = await BiliApi.join_guard(room_id, gift_id, cookie)
        if r:
            logging.info(f"GUARD AC SUCCESS! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
        else:
            logging.critical(f"GUARD AC FAILED! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
            if "访问被拒绝" in msg:
                await self.add_black_list(cookie)

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

        cookies, black_list = await self.load_cookie()
        for i in range(len(cookies)):
            if i in black_list:
                uid_list = re.findall(r"DedeUserID=(\d+)", cookies[i])
                user_id = uid_list[0] if uid_list else "Unknown-uid"
                logging.warning(f"User {i}-{user_id} in black list, skip it.")
            else:
                await process_fn(i, room_id, gift_id, cookies[i])

    async def run_forever(self):
        while True:
            r = await self.q.get()
            await self.accept_prize(r)


async def main():
    a = Acceptor()

    async def on_price_message(key):
        logging.info(f"Acceptor: Prize message key received from server: {key}")
        await a.add_task(key)
    c = ReConnectingWsClient(uri="ws://%s:%s" % PRIZE_HANDLER_SERVE_ADDR, on_message=on_price_message)
    await c.start()
    await a.run_forever()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
