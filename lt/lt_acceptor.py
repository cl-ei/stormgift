import time
import json
import asyncio
import requests
import traceback
from random import random
from utils.biliapi import BiliApi
from utils.dao import redis_cache
from config import cloud_acceptor_url
from utils.mq import mq_raffle_to_acceptor
from utils.highlevel_api import DBCookieOperator
from config.log4 import acceptor_logger as logging
from utils.reconstruction_model import UserRaffleRecord, objects


NON_SKIP_USER_ID = [
    20932326,  # DD
    39748080,  # LP
]


class Worker(object):
    def __init__(self, index):
        self.worker_index = index
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

    async def proc_single(self, key):

        key_type, room_id, gift_id = key.split("$")
        room_id = int(room_id)
        gift_id = int(gift_id)
        if not self._is_new_gift(key_type, room_id, gift_id):
            return "Repeated gift, skip it."

        non_skip, normal_objs = await self.load_cookie()
        user_cookie_objs = non_skip + normal_objs
        cookies = []
        for c in user_cookie_objs:
            cookies.append(c.cookie)

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
        try:
            r = requests.post(url=cloud_acceptor_url, json=req_json, timeout=20)
        except Exception as e:
            logging.error(f"Cannot access cloud acceptor! e: {e}")
            return

        if r.status_code != 200:
            return logging.error(f"Accept Failed! e: {r.content.decode('utf-8')}")

        result_list = json.loads(r.content.decode('utf-8'))
        index = 0
        for cookie_obj in user_cookie_objs:
            flag, message = result_list[index]
            index += 1

            if flag is not True:
                if "访问被拒绝" in message:
                    await DBCookieOperator.set_blocked(cookie_obj)
                    self._cookie_objs_update_time = 0
                elif "请先登录哦" in message:
                    await DBCookieOperator.set_invalid(cookie_obj)
                    self._cookie_objs_update_time = 0

                if index != 0:
                    message = message[:100]
                logging.warning(
                    f"{act.upper()} FAILED! {index}-{cookie_obj.name}({cookie_obj.uid}) "
                    f"@{room_id}${gift_id}, message: {message}"
                )

            else:
                if act == "join_pk":
                    try:
                        r = await UserRaffleRecord.create(cookie_obj.uid, "PK", gift_id)
                        r = f"{r.id}"
                    except Exception as e:
                        r = f"UserRaffleRecord create Error: {e}"

                elif act == "join_guard":
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
                        r = await UserRaffleRecord.create(cookie_obj.uid, gift_name, gift_id)
                        r = f"{r.id}"
                    except Exception as e:
                        r = f"UserRaffleRecord create Error: {e}"

                elif act == "join_tv":
                    try:
                        info = await redis_cache.get(f"T${room_id}${gift_id}")
                        gift_name = info["gift_name"]
                        r = await UserRaffleRecord.create(cookie_obj.uid, gift_name, gift_id)
                        r = f"{r.id}"
                    except Exception as e:
                        r = f"UserRaffleRecord create Error: {e}"

                else:
                    r = f"UserRaffleRecord create Error: Key Error."

                logging.info(
                    f"{act.upper()} OK! {index}-{cookie_obj.uid}-{cookie_obj.name} "
                    f"@{room_id}${gift_id}. message: {message}. p: {r}"
                )

    async def run_forever(self):
        while True:
            message, has_read = await mq_raffle_to_acceptor.get()

            start_time = time.time()
            task_id = f"{int(str(random())[2:]):x}"
            logging.info(f"Acceptor Task {self.worker_index}-[{task_id}] start...")

            try:
                r = await self.proc_single(message)
            except Exception as e:
                logging.error(f"Acceptor Task {self.worker_index}-[{task_id}] error: {e}, {traceback.format_exc()}")
            else:
                cost_time = time.time() - start_time
                logging.info(f"Acceptor Task {self.worker_index}-[{task_id}] success, r: {r}, cost: {cost_time:.3f}")
            finally:
                await has_read()


async def main():
    logging.info("-" * 80)
    logging.info("LT ACCEPTOR started!")
    logging.info("-" * 80)
    await objects.connect()

    tasks = [asyncio.create_task(Worker(index).run_forever()) for index in range(4)]
    for t in tasks:
        await t

loop = asyncio.get_event_loop()
loop.run_until_complete(main())


asyncio.get_event_loop().run_until_complete(main())
