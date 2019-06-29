import time
import asyncio
from utils.biliapi import BiliApi
from utils.dao import CookieOperator
from config.log4 import bili_api_logger as logging


class ReqFreLimitApi(object):
    __req_time = {}

    @classmethod
    async def _wait(cls, f, wait_time):
        last_req_time = cls.__req_time.get(f)
        if last_req_time is None:
            cls.__req_time[f] = time.time()
        else:
            interval = time.time() - last_req_time
            print(interval)
            if interval < wait_time:
                sleep_time = wait_time - interval
                logging.warn(f"f: {f}, sleep_time: {sleep_time:.3f}")
                await asyncio.sleep(sleep_time)
            cls.__req_time[f] = time.time()

    @classmethod
    async def _update_time(cls, f):
        cls.__req_time[f] = time.time()

    @classmethod
    async def get_uid_by_name(cls, user_name, wait_time=2):
        await cls._wait("get_uid_by_name", wait_time=wait_time)

        flag, uid = await BiliApi.get_user_id_by_search_way(user_name)
        if flag and isinstance(uid, (int, float)) and uid > 0:
            return uid

        cookie = CookieOperator.get_cookie_by_uid("*")
        if not cookie:
            return None

        uid = None
        for retry_time in range(3):
            await BiliApi.add_admin(user_name, cookie)

            flag, admin_list = await BiliApi.get_admin_list(cookie)
            if not flag:
                continue

            for admin in admin_list:
                if admin.get("uname") == user_name:
                    uid = admin.get("uid")
                    break

        if isinstance(uid, (int, float)) and uid > 0:
            await BiliApi.remove_admin(uid, cookie)

        await cls._update_time("get_uid_by_name")
        return uid
