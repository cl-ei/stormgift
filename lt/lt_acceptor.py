import re
import time
import asyncio
import traceback
from random import random
from utils.dao import BiliUserInfoCache, RaffleMessageQ
from utils.biliapi import BiliApi
from config.log4 import acceptor_logger as logging


BiliApi.USE_ASYNC_REQUEST_METHOD = True

NON_SKIP_USER_ID = [
    20932326,  # DD
    39748080,  # LP
]


class Acceptor(object):
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
        return r, msg

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
        return r, msg

    async def proc_single(self, msg):
        key, created_time, *_ = msg
        if time.time() - created_time > 20:
            logging.error(f"Message Expired ! created_time: {created_time}")

        key_type, room_id, gift_id = key.split("$")
        room_id = int(room_id)
        gift_id = int(gift_id)

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
        prize_timeout = False
        for user_id, cookie in white_cookies:
            display_index += 1

            if prize_timeout:
                user_name = await BiliUserInfoCache.get_user_name_by_user_id(user_id)
                logging.info(f"Gift time out! user {display_index}-{user_name}({user_id})")
                continue

            if busy_412:
                if random() < 0.3:
                    user_name = await BiliUserInfoCache.get_user_name_by_user_id(user_id)
                    logging.info(f"Too busy, user {display_index}-{user_name}({user_id}) skip. reason: 412.")
                    continue
                else:
                    await asyncio.sleep(0.1)

            flag, msg = await process_fn(display_index, user_id, room_id, gift_id, cookie)
            if not flag and "抽奖已过期" in msg:
                prize_timeout = True

    async def run(self):
        while True:
            msg = await RaffleMessageQ.get(timeout=50)
            if msg is None:
                continue

            start_time = time.time()
            task_id = str(random())[2:]
            logging.info(f"Acceptor Task[{task_id}] start...")

            try:
                r = await self.proc_single(msg)
            except Exception as e:
                logging.error(f"Acceptor Task[{task_id}] error: {e}, {traceback.format_exc()}")
            else:
                cost_time = time.time() - start_time
                logging.info(f"Acceptor Task[{task_id}] success, r: {r}, cost time: {cost_time:.3f}")


async def main():
    logging.warning("Starting LT acceptor process...")
    acceptor = Acceptor()
    await acceptor.run()
    logging.warning("LT acceptor process shutdown!")


asyncio.get_event_loop().run_until_complete(main())
