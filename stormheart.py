import sys
import time
import asyncio
from random import randint
from utils.biliapi import BiliApi
from config.g import LIVE_ROOM_ID_DD
from src.api.schemas import *
from src.api.bili import BiliPublicApi, BiliPrivateApi
from src.db.queries.queries import queries, LTUser
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

    LIVE_STATUS_CHECK_INTERVAL = 60 * 2  # 2分钟内不再检查直播间状态

    def __init__(self, user_id: int):
        self.user_id = user_id
        self._last_check_time = 0

    async def get_live_room_status(self, room_id: int) -> bool:
        if not room_id:
            return False

        if time.time() - self._last_check_time < self.LIVE_STATUS_CHECK_INTERVAL:
            return True

        flag, status = await BiliApi.get_live_status(room_id)
        logging.info(f"Check live room status: room_id: {room_id} -> status: {status}")
        if not flag:
            raise RuntimeError(f"BiliApi Exception: {status}")

        if status:
            self._last_check_time = time.time()
        return status

    async def find_living_room(self) -> Optional[int]:
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
                room_id = r.short_id or r.room_id
                logging.info(f"Find live room for user {self.user_id} -> room_id: {room_id}")
                return room_id
            await asyncio.sleep(2)

    @staticmethod
    async def small_heartbeat(room_id: int, api: BiliPrivateApi):
        next_interval = randint(5, 50)
        while True:
            await asyncio.sleep(next_interval)
            next_interval = await api.storm_heart_beat(
                previous_interval=next_interval, room_id=room_id)

    async def run(self):
        room_id = LIVE_ROOM_ID_DD
        user = await queries.get_lt_user_by_uid(self.user_id)
        if not user:
            logging.error(F"User need login: {self.user_id}")
            return

        api = BiliPrivateApi(req_user=user)

        bags = await api.get_bag_list(room_id)
        logging.info(f"Init bags: {bags}")

        hbe = await api.storm_heart_e(room_id)
        _s = self.small_heartbeat(room_id=room_id, api=api)
        small_hb_task = asyncio.create_task(_s)
        for hbx_index in range(1, 8):
            await asyncio.sleep(hbe.heartbeat_interval)
            hbe = await api.storm_heart_x(hbx_index, hbe, room_id)
            await api.receive_heart_gift(room_id)
            bags = await api.get_bag_list(room_id)
            logging.info(f"storm_heart_x: {hbe}\n\tbags: {bags}")

        small_hb_task.cancel()


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
        *[StormHeart(user.uid).run() for user in users]
    )
    print(f"users {len(users)}: {users}")
    await redis_cache.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
