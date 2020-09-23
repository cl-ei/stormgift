import sys
import asyncio
import traceback
from random import randint
from utils.dao import redis_cache
from config.g import LIVE_ROOM_ID_DD
from config.log4 import get_logger
from src.api.schemas import *
from src.api.bili import BiliPrivateApi
from src.db.clients.mongo import db
from src.db.queries.cron_action import get_or_create_today_rec
from src.db.queries.queries import queries, LTUser


logging = get_logger("c_storm_heart")


MEDAL_ID_TO_ROOM_ID = {
    123: 23058,  # 3号直播间
    # 142679: LIVE_ROOM_ID_DD,
}


async def auto_shutdown():
    await asyncio.sleep(3600 * 14)
    logging.info(f"已运行14小时，现在重启.")
    sys.exit(0)


class StormHeart:

    TaskDone = type("TaskDone", (Exception, ), {})

    def __init__(self, user_id: int):
        self.user_id = user_id

        self.user: Optional[LTUser] = None
        self.api: Optional[BiliPrivateApi] = None

        self.room_id = 0
        self.__st = None

    async def get_live_room(self):
        medals = await self.api.get_user_owned_medals()
        for m in medals:
            room_id = MEDAL_ID_TO_ROOM_ID.get(m.medal_id)
            if room_id is not None:
                self.room_id = room_id
                return

    async def record_heart_logs(self, message: str):
        act_rec = await get_or_create_today_rec(self.user_id)
        message = f"{datetime.datetime.now()}: {message}"
        act_rec.storm_heart_logs.append(message)
        await act_rec.save(db, fields=("storm_heart_logs", ))
        logging.debug(f"LOG: {message}")

    async def get_7d_heart_count(self) -> int:
        bags = await self.api.get_bag_list(self.room_id)
        count = 0
        for b in bags:
            if b.corner_mark == "7天" and b.gift_name == "小心心":
                count += b.gift_num
        return count

    async def check_bags_and_stop_task(self) -> int:
        current_heart_count = await self.get_7d_heart_count()
        act_rec = await get_or_create_today_rec(self.user_id)
        act_rec.storm_heart_gift_record.insert(0, current_heart_count)
        await act_rec.save(db, fields=("storm_heart_gift_record", ))

        rc = act_rec.storm_heart_gift_record
        if len(rc) >= 4 and rc[0] <= rc[1] <= rc[2] <= rc[3]:
            raise self.TaskDone()
        return current_heart_count

    @staticmethod
    async def small_heartbeat(room_id: int, api: BiliPrivateApi):
        next_interval = randint(5, 50)
        while True:
            await asyncio.sleep(next_interval)
            next_interval = await api.storm_heart_beat(
                previous_interval=next_interval, room_id=room_id)

    async def _run_in_catcher(self):
        await self.get_live_room()
        room_id = self.room_id

        if not room_id:
            logging.error(f"{self.user} 没有获取到可以挂载的直播间，现在退出。")
            return

        message = f"{self.user} 寻找到挂载的直播间：{self.room_id}"
        logging.info(message)
        await self.record_heart_logs(message)

        hbe = await self.api.storm_heart_e(room_id)

        _s = self.small_heartbeat(room_id=room_id, api=self.api)
        self.__st = asyncio.create_task(_s)

        cnt = await self.check_bags_and_stop_task()
        await self.record_heart_logs(f"{self.api.req_user} 发送初始心跳成功！小心心数：{cnt}, hbe: {hbe}")

        for hbx_index in range(1, 300):
            await asyncio.sleep(hbe.heartbeat_interval)
            hbe = await self.api.storm_heart_x(hbx_index, hbe, room_id)
            cnt = await self.check_bags_and_stop_task()
            await self.record_heart_logs(f"{self.api.req_user} 发生X心跳成功！小心心数：{cnt}, hbe: {hbe}")

    async def run(self):
        self.user = user = await queries.get_lt_user_by_uid(self.user_id)
        self.api = BiliPrivateApi(req_user=user)

        try:
            await self._run_in_catcher()

        except self.TaskDone:
            logging.info(f"{user} 小心心挂机结束。")
            await self.record_heart_logs(f"发现小心心不再增加，今日挂机结束。")

        except Exception as e:
            message = f"{user} 在小心心挂机中发生错误: {e}\n{traceback.format_exc()}"
            logging.error(message)
            await self.record_heart_logs(message)

        finally:
            if self.__st and not self.__st.done():
                self.__st.cancel()
                self.__st = None


async def main():
    users: List[LTUser] = await queries.get_all_lt_user()
    users = [u for u in users if u.storm_heart is True]
    logging.info(f"Storm heart started. users {len(users)}: \n\t{users}")
    await asyncio.gather(
        auto_shutdown(),
        *[StormHeart(user.uid).run() for user in users]
    )
    await redis_cache.close()
