import time
import asyncio
import traceback
from random import random
from utils.biliapi import BiliApi
from utils.highlevel_api import DBCookieOperator
from utils.dao import RaffleMessageQ, redis_cache
from config.log4 import acceptor_logger as logging
from utils.reconstruction_model import UserRaffleRecord, objects


BiliApi.USE_ASYNC_REQUEST_METHOD = True

NON_SKIP_USER_ID = [
    20932326,  # DD
    39748080,  # LP
]


class Acceptor(object):
    def __init__(self):
        self.__busy_time = 0
        self.accepted_keys = []

        self._cookie_objs_non_skip = []
        self._cookie_objs = []
        self._cookie_objs_update_time = 0

    def _is_new_gift(self, *args):
        key = "$".join([str(_) for _ in args])
        if key in self.accepted_keys:
            return False

        self.accepted_keys.insert(0, key)

        while len(self.accepted_keys) >= 10000:
            self.accepted_keys.pop()

        return True

    async def load_cookie(self):
        if time.time() - self._cookie_objs_update_time > 100:

            logging.info("Now update cached user_cookie_objs.")

            objs = await DBCookieOperator.get_objs(available=True, non_blocked=True, separate=True)
            self._cookie_objs_non_skip, self._cookie_objs = objs
            self._cookie_objs_update_time = time.time()

        return self._cookie_objs_non_skip, self._cookie_objs

    async def accept_tv(self, index, user_cookie_obj, room_id, gift_id):

        cookie = user_cookie_obj.cookie
        user_id = user_cookie_obj.DedeUserID
        user_name = user_cookie_obj.name

        r, msg = await BiliApi.join_tv(room_id, gift_id, cookie)
        if r:
            try:
                info = await redis_cache.get(f"T${room_id}${gift_id}")
                gift_name = info["gift_name"]
                r = await UserRaffleRecord.create(user_id, gift_name, gift_id)
                r = f"obj.id: {r.id}"
            except Exception as e:
                r = f"UserRaffleRecord create Error: {e}"
            logging.info(f"TV SUCCESS! {index}-{user_name}({user_id}) - {room_id}${gift_id}, msg: {msg}, db r: {r}")

        else:
            if "412" in msg:
                self.__busy_time = time.time()

            elif "访问被拒绝" in msg:
                await DBCookieOperator.set_blocked(user_cookie_obj)
                self._cookie_objs_update_time = 0

            elif "请先登录哦" in msg:
                await DBCookieOperator.set_invalid(user_cookie_obj)
                self._cookie_objs_update_time = 0

            if index != 0:
                msg = msg[:100]

            logging.warn(f"TV AC FAILED! {index}-{user_name}({user_id}), key: {room_id}${gift_id}, msg: {msg}")

        return r, msg

    async def accept_guard(self, index, user_cookie_obj, room_id, gift_id):

        cookie = user_cookie_obj.cookie
        user_id = user_cookie_obj.DedeUserID
        user_name = user_cookie_obj.name

        r, msg = await BiliApi.join_guard(room_id, gift_id, cookie)
        if r:
            try:
                info = await redis_cache.get(f"G${room_id}${gift_id}")
                privilege_type = info["privilege_type"]
                if privilege_type == 3:
                    gift_name = "舰长"
                elif privilege_type == 2:
                    gift_name = "提督"
                elif privilege_type == 1:
                    gift_name = "总督"
                else:
                    gift_name = "大航海"
                r = await UserRaffleRecord.create(user_id, gift_name, gift_id)
                r = f"obj.id: {r.id}"
            except Exception as e:
                r = f"UserRaffleRecord create Error: {e}"

            logging.info(f"GUARD SUCCESS! {index}-{user_name}({user_id}) - {room_id}${gift_id}, msg: {msg}, db r: {r}")

        else:
            if "412" in msg or "Not json response" in msg:
                self.__busy_time = time.time()

            elif "访问被拒绝" in msg:
                await DBCookieOperator.set_blocked(user_cookie_obj)
                self._cookie_objs_update_time = 0

            elif "请先登录哦" in msg:
                await DBCookieOperator.set_invalid(user_cookie_obj)
                self._cookie_objs_update_time = 0

            if index != 0:
                msg = msg[:100]

            logging.warning(f"GUARD AC FAILED! {index}-{user_name}({user_id}), key: {room_id}${gift_id}, msg: {msg}")

        return r, msg

    async def accept_pk(self, index, user_cookie_obj, room_id, gift_id):

        cookie = user_cookie_obj.cookie
        user_id = user_cookie_obj.DedeUserID
        user_name = user_cookie_obj.name

        r, msg = await BiliApi.join_pk(room_id, gift_id, cookie)
        if r:
            logging.info(f"GUARD SUCCESS! {index}-{user_name}({user_id}) - {room_id}${gift_id}, msg: {msg}, db r: {r}")

            try:
                gift_name = "PK"
                r = await UserRaffleRecord.create(user_id, gift_name, gift_id)
                r = f"obj.id: {r.id}"
            except Exception as e:
                r = f"UserRaffleRecord create Error: {e}"

        else:
            if "412" in msg or "Not json response" in msg:
                self.__busy_time = time.time()

            elif "访问被拒绝" in msg:
                await DBCookieOperator.set_blocked(user_cookie_obj)
                self._cookie_objs_update_time = 0

            elif "请先登录哦" in msg:
                await DBCookieOperator.set_invalid(user_cookie_obj)
                self._cookie_objs_update_time = 0

            if index != 0:
                msg = msg[:100]

            logging.warning(f"GUARD AC FAILED! {index}-{user_name}({user_id}), key: {room_id}${gift_id}, msg: {msg}")

        return r, msg

    async def proc_single(self, msg):
        key, created_time, *_ = msg
        if time.time() - created_time > 20:
            logging.error(f"Message Expired ! created_time: {created_time}")
            return

        key_type, room_id, gift_id = key.split("$")
        room_id = int(room_id)
        gift_id = int(gift_id)

        if key_type in "TGP":
            non_skip, normal_objs = await self.load_cookie()
            cookies = []
            for c in non_skip + normal_objs:
                cookies.append(c.cookie)

            req_url = "https://service-ir5wks32-1251734549.gz.apigw.tencentcs.com/release/test"
            if key_type == "T":
                act = "join_tv"
            elif key_type == "G":
                act = "join_guard"
            elif key_type == "P":
                act = "join_pk"
            else:
                return

            req_json = {
                "act": act,
                "room_id": room_id,
                "gift_id": gift_id,
                "cookies": cookies
            }

            import requests
            r = requests.post(url=req_url, json=req_json)
            logging.info(f"User new method acceptor: code: {r.status_code}, result: {r.content.decode('utf-8')}")
            return

        if key_type == "T":
            process_fn = self.accept_tv
        elif key_type == "G":
            process_fn = self.accept_guard
        elif key_type == "P":
            process_fn = self.accept_pk
        else:
            return "Error Key."

        if not self._is_new_gift(key_type, room_id, gift_id):
            return "Repeated gift, skip it."

        non_skip, normal_objs = await self.load_cookie()

        display_index = -1
        for obj in non_skip:
            display_index += 1
            await process_fn(display_index, obj, room_id, gift_id)

        busy_412 = bool(time.time() - self.__busy_time < 60 * 20)
        for user_cookie_obj in normal_objs:

            display_index += 1
            user_id = user_cookie_obj.DedeUserID
            user_name = user_cookie_obj.name

            if busy_412:
                if random() < 0.5:
                    logging.info(f"Too busy, user {display_index}-{user_name}({user_id}) skip. reason: 412.")
                    continue
                await asyncio.sleep(0.5)

            flag, msg = await process_fn(display_index, user_cookie_obj, room_id, gift_id)
            if not flag and ("抽奖已过期" in msg or "已经过期啦" in msg):
                logging.warning(f"Prize expired! now skip all!")
                return

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
    await objects.connect()

    acceptor = Acceptor()
    await acceptor.run()
    logging.warning("LT acceptor process shutdown!")


asyncio.get_event_loop().run_until_complete(main())
