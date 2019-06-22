import os
import re
import sys
import time
import asyncio
import datetime
import traceback
from aiohttp import web
from queue import Empty
from random import random
from utils.dao import BiliUserInfoCache
from multiprocessing import Process, Queue
from utils.biliapi import BiliApi
from config.log4 import acceptor_logger as logging
from config import LT_ACCEPTOR_HOST, LT_ACCEPTOR_PORT

# ACCEPT URL: http://127.0.0.1:30001?action=prize_key&key_type=T&room_id=123&gift_id=1233


NON_SKIP_USER_ID = [
    20932326,  # DD
    39748080,  # LP
]


class Executor(object):
    def __init__(self):
        self.__busy_time = 0

        self.cookie_file = "data/valid_cookies.txt"
        self.__block_list = {}
        self.accepted_keys = []

    def _is_new_gift(self, *args):
        key = "$".join([str(_) for _ in args])
        if key in self.accepted_keys:
            return False

        self.accepted_keys.insert(0, key)

        while len(self.accepted_keys) >= 10000:
            self.accepted_keys.pop()

        return True

    async def add_to_block_list(self, cookie):
        self.__block_list[cookie] = time.time()
        user_ids = re.findall(r"DedeUserID=(\d+)", "".join(self.__block_list.keys()))
        block_display_str = ", ".join([
            f"{await BiliUserInfoCache.get_user_name_by_user_id(uid)}({uid})" for uid in user_ids
        ])
        logging.critical(f"Black list updated. current {len(user_ids)}: [{block_display_str}].")

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
        blocked_list = []

        now = time.time()
        t_12_hours = 3600 * 12
        for cookie in cookies:
            user_id = int(re.findall(r"DedeUserID=(\d+)", cookie)[0])
            block_time = self.__block_list.get(cookie)
            if isinstance(block_time, (int, float)) and now - block_time < t_12_hours:
                blocked_list.append(user_id)
                continue

            if user_id in NON_SKIP_USER_ID:
                non_skip_cookies.append((user_id, cookie))
            else:
                white_cookies.append((user_id, cookie))

        user_display_info = ", ".join([
            f"{await BiliUserInfoCache.get_user_name_by_user_id(uid)}({uid})" for uid in blocked_list
        ])
        logging.info(f"Blocked users: [{user_display_info}], now skip.")

        # GC
        if len(self.__block_list) > len(cookies):
            new_block_list = {}
            for cookie in self.__block_list:
                if cookie in cookies:
                    new_block_list[cookie] = self.__block_list[cookie]
            self.__block_list = new_block_list

        return non_skip_cookies, white_cookies

    async def accept_tv(self, index, user_id, room_id, gift_id, cookie):
        r, msg = await BiliApi.join_tv(room_id, gift_id, cookie)
        user_name = await BiliUserInfoCache.get_user_name_by_user_id(user_id)
        if r:
            logging.info(f"TV AC SUCCESS! {index}-{user_name}({user_id}), key: {room_id}${gift_id}, msg: {msg}")
        else:
            logging.critical(f"TV AC FAILED! {index}-{user_name}({user_id}), key: {room_id}${gift_id}, msg: {msg}")
            if "访问被拒绝" in msg:
                await self.add_to_block_list(cookie)

            elif "412" in msg:
                self.__busy_time = time.time()

    async def accept_guard(self, index, user_id, room_id, gift_id, cookie):
        r, msg = await BiliApi.join_guard(room_id, gift_id, cookie)
        user_name = await BiliUserInfoCache.get_user_name_by_user_id(user_id)
        if r:
            logging.info(f"GUARD AC SUCCESS! {index}-{user_name}({user_id}), key: {room_id}${gift_id}, msg: {msg}")
        else:
            logging.critical(f"GUARD AC FAILED! {index}-{user_name}({user_id}), key: {room_id}${gift_id}, msg: {msg}")
            if "访问被拒绝" in msg:
                await self.add_to_block_list(cookie)

            elif "412" in msg:
                self.__busy_time = time.time()

    async def __call__(self, args):
        key_type, room_id, gift_id, *_ = args

        if key_type == "T":
            process_fn = self.accept_tv
        elif key_type == "G":
            process_fn = self.accept_guard
        else:
            return "Error Key."

        if not self._is_new_gift(key_type, room_id, gift_id):
            return "Repeated gift, skip it."

        non_skip_cookies, white_cookies = await self.load_uid_and_cookie()

        display_index = -1
        for user_id, cookie in non_skip_cookies:
            display_index += 1
            await process_fn(display_index, user_id, room_id, gift_id, cookie)

        busy_412 = bool(time.time() - self.__busy_time < 60 * 20)
        for user_id, cookie in white_cookies:
            display_index += 1

            if busy_412:
                if random() < 0.3:
                    user_name = await BiliUserInfoCache.get_user_name_by_user_id(user_id)
                    logging.info(
                        f"Too busy, user {display_index}-{user_name}({user_id}) skip. "
                        f"reason: 412."
                    )
                    continue
                else:
                    await asyncio.sleep(0.1)
            await process_fn(display_index, user_id, room_id, gift_id, cookie)


class AsyncHTTPServer(object):
    def __init__(self, q, host="127.0.0.1", port=8080):
        self.__q = q
        self.host = host
        self.port = port

    async def handler(self, request):
        action = request.query.get("action")
        if action != "prize_key":
            return web.Response(text=f"Error Action.", content_type="text/html")

        try:
            key_type = request.query.get("key_type")
            room_id = int(request.query.get("room_id"))
            gift_id = int(request.query.get("gift_id"))
            assert room_id > 0 and gift_id > 0 and key_type in ("T", "G")
        except Exception as e:
            error_message = f"Param Error: {e}."
            return web.Response(text=error_message, content_type="text/html")

        self.__q.put_nowait((key_type, room_id, gift_id))
        return web.Response(text=f"OK", content_type="text/html")

    def __call__(self):
        app = web.Application()
        app.add_routes([web.get('/', self.handler)])

        logging.info(f"Start server on: {self.host}:{self.port}")
        try:
            web.run_app(app, host=self.host, port=self.port)
        except Exception as e:
            logging.exception(f"Exception: {e}\n", exc_info=True)


class AsyncWorker(object):
    def __init__(self, http_server_proc, q, target):
        self.__http_server = http_server_proc
        self.__q = q
        self.__exc = target

    async def handler(self):
        while True:
            fe_status = self.__http_server.is_alive()
            if not fe_status:
                logging.error(f"Http server is not alive! exit now.")
                sys.exit(1)

            try:
                msg = self.__q.get(timeout=3)
            except Empty:
                continue

            start_time = time.time()
            logging.info(f"LT_ACCEPTOR Task starting... msg: {msg}")
            try:
                r = await self.__exc(msg)
            except Exception as e:
                r = f"Error: {e}, {traceback.format_exc()}"
            cost_time = time.time() - start_time
            logging.info(f"LT_ACCEPTOR Task finished. cost time: {cost_time:.3f}, result: {r}")

    def __call__(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.handler())


def main():
    logging.warning("Starting LT acceptor process...")

    for line in os.popen(f'lsof -i:{LT_ACCEPTOR_PORT}').readlines():
        line = line.strip()
        parts = line.split()
        if (
            len(parts) > 8
            and parts[0] == "python3.7"
            and str(LT_ACCEPTOR_PORT) in parts[-2]
            and parts[-3] == "TCP"
        ):
            existed_proc_number = int(parts[1])
            logging.warn(
                f"\nLT acceptor process already existed:\n"
                f"[{line}]\n"
                f"now exec `kill -9 {existed_proc_number}`..."
            )
            r = os.system(f"kill -9 {existed_proc_number}")
            logging.info(f"Process {existed_proc_number} killed. result: {r}")
            time.sleep(0.2)
            break

    q = Queue()

    server = AsyncHTTPServer(q=q, host=LT_ACCEPTOR_HOST, port=LT_ACCEPTOR_PORT)
    p = Process(target=server, daemon=True)
    p.start()

    worker = AsyncWorker(p, q=q, target=Executor())
    worker()

    logging.warning("LT acceptor process shutdown!")


if __name__ == "__main__":
    main()
