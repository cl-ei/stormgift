import sys
import time
import asyncio
import datetime
from random import randint
from typing import Optional
from utils.biliapi import BiliApi
from src.api.bili import BiliPublicApi, BiliPrivateApi
from db.queries import queries, LTUser, List
from utils.dao import redis_cache
from config.log4 import crontab_task_logger as logging


async def auto_shutdown():
    while True:
        today_key = f"STORM:HT:{datetime.datetime.now().date()}"
        r = await redis_cache.set_if_not_exists(key=today_key, value=1)
        if r:
            logging.info(f"今日未重启，现在重启.")
            sys.exit(0)
        await asyncio.sleep(60)


class StormHeart:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.room_id: int = 0

        self._last_check_time = 0
        self.check_interval = 60 * 2

    async def get_live_room_status(self) -> bool:
        if not self.room_id:
            return False

        if time.time() - self._last_check_time < self.check_interval:
            return True

        flag, status = await BiliApi.get_live_status(self.room_id)
        logging.info(f"Check live room status: {self.room_id} -> {status}")
        if not flag:
            raise RuntimeError(f"BiliApi Exception: {status}")

        if status:
            self._last_check_time = time.time()
        return status

    async def find_living_room(self) -> None:
        flag, data = await BiliApi.get_user_medal_list(self.user_id)
        if not flag:
            return

        medals = list(data[str(self.user_id)]["medal"].values())
        master_id_list = [m["master_id"] for m in medals]
        api = BiliPublicApi()
        for master_id in master_id_list:
            r = await api.get_live_room_info(user_id=master_id)
            if r.liveStatus != 1:
                await asyncio.sleep(2)
                continue

            r = await api.get_live_room_detail(r.roomid)
            if r:
                self.room_id = r.short_id or r.room_id
                logging.info(f"Find live room for user {self.user_id} -> {self.room_id}")
                return
            await asyncio.sleep(2)

    async def post_heartbeat_once(self, next_interval: int) -> int:
        user = await queries.get_lt_user_by_uid(self.user_id)
        if user is None:
            return 0

        api = BiliPrivateApi(req_user=user)
        next_interval = await api.post_web_hb(previous_interval=next_interval, room_id=self.room_id)
        return next_interval

    async def run(self):
        next_interval = randint(6, 30)
        while True:
            is_living = await self.get_live_room_status()
            if not is_living:
                await self.find_living_room()

            if not self.room_id:
                await asyncio.sleep(60*5)

            try:
                next_interval = await self.post_heartbeat_once(next_interval)
            except Exception as e:
                _ = e
                next_interval = 1

            if next_interval > 0:
                await asyncio.sleep(next_interval)
            else:
                return


async def check_package(room_id: int = None):
    while True:
        user = await queries.get_lt_user_by_uid("TZ")
        api = BiliPrivateApi(user)
        data = await api.get_bag_list(room_id)
        print(data)
        await asyncio.sleep(60)


async def main():
    # users: List[LTUser] = await queries.get_all_lt_user()
    users = [await queries.get_lt_user_by_uid("TZ")]
    await asyncio.gather(
        auto_shutdown(),
        check_package(13369254),
        *[StormHeart(user.uid).run() for user in users]
    )
    print(f"users {len(users)}: {users}")
    await redis_cache.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
