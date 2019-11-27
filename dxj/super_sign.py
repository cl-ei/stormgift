import time
import datetime
import asyncio
from utils.ws import RCWebSocketClient
from utils.biliapi import BiliApi, WsApi
from utils.dao import redis_cache
from config.log4 import config_logger
from utils.highlevel_api import DBCookieOperator

logging = config_logger("super_sign")

send_danmak_rooms = [
    13369254,
    2516117,
]

expected = [
    # 910884,  # 浙江共青团
    13369254,
    2516117,
]


class SignRecord:

    def __init__(self, room_id):
        self.key_root = F"LT_SIGN_{room_id}"

    async def sign(self, user_id):
        """

        :param user_id:
        :return: sign success. continue, total, rank
        """
        ukey = f"{self.key_root}_{user_id}"
        offset = 0
        today_str = str(datetime.datetime.now().date() + datetime.timedelta(days=offset))
        yesterday = str(datetime.datetime.now().date() - datetime.timedelta(days=1) + datetime.timedelta(days=offset))

        continue_key = f"{ukey}_c"
        total_key = f"{ukey}_t"

        user_today = f"{ukey}_{today_str}"
        sign_success = await redis_cache.set_if_not_exists(key=user_today, value=1, timeout=3600*36)
        continue_days = None
        total_days = None

        if sign_success:

            today_sign_key = f"{self.key_root}_{total_key}_sign_count"
            today_sign_count = await redis_cache.incr(key=today_sign_key)
            await redis_cache.expire(key=today_sign_key, timeout=3600*24)
            dec_score = 0.001*int(today_sign_count)

            user_yesterday = f"{self.key_root}_{user_id}_{yesterday}"

            if not await redis_cache.get(user_yesterday):
                await redis_cache.delete(continue_key)

            continue_days = await redis_cache.incr(continue_key)
            total_days = await redis_cache.incr(total_key)

            incr_score = 50 + min(84, 12 * (continue_days - 1)) - dec_score
            await redis_cache.sorted_set_zincr(key=self.key_root, member=user_id, increment=incr_score)

        if continue_days is None:
            continue_days = int(await redis_cache.get(continue_key))
        if total_days is None:
            total_days = int(await redis_cache.get(total_key))

        rank = await redis_cache.sorted_set_zrank(key=self.key_root, member=user_id)
        return bool(sign_success), continue_days, total_days, rank + 1


async def send_danmaku(msg, room_id, user="DD"):
    cookie_obj = await DBCookieOperator.get_by_uid(user_id=user)
    if not cookie_obj:
        logging.error(f"Cannot get cookie for user: {user}. danmaku send failed.")
        return

    flag, msg = await BiliApi.send_danmaku(
        message=msg,
        room_id=room_id,
        cookie=cookie_obj.cookie
    )
    if not flag:
        logging.error(f"Danmaku [{msg}] send failed, msg: {msg}, user: {user}.")


class DanmakuProcessor:
    def __init__(self, q, room_id, short_room_id=None, name="??"):
        self.q = q
        self.room_id = room_id
        self.short_room_id = short_room_id or room_id
        self.name = name

        self._cached_settings = None
        self._settings_expire_time = 0

        self._is_live = False
        self._last_live_time = 0

        self.gift_list = []
        self.carousel_msg_counter = 100
        self.carousel_msg_index = 0

        self.cookie = ""
        self.cookie_expire_time = None

        self.msg_speed_counter = 0
        self.msg_speed_counter_start_time = 0
        self.msg_block_until = 0

        self.master_uid = None
        self.followers = []

        self.s = SignRecord(room_id=room_id)

    async def proc_one_danmaku(self, dmk):
        cmd = dmk.get("cmd", "") or ""
        if cmd.startswith("DANMU_MSG"):
            info = dmk.get("info", {})
            msg = str(info[1])
            uid = info[2][0]
            user_name = info[2][1]
            is_admin = info[2][2]
            ul = info[4][0]
            d = info[3]
            dl = d[0] if d else "-"
            deco = d[1] if d else "undefined"
            if msg not in ("签到", "打卡"):
                return

            sign, conti, total, rank = await self.s.sign(user_id=uid)
            if self.room_id not in send_danmak_rooms:
                return

            prompt = f"{msg}成功！" if sign else f"已{msg}，"
            message = f"{user_name}{prompt}连续{msg}{conti}天、累计{total}天，排名第{rank}."

            dmk_user = "DD" if self.room_id != 2516117 else "LP"
            if len(message) < 30:
                await send_danmaku(msg=message[:29], room_id=self.room_id, user=dmk_user)
                return

            await send_danmaku(msg=message[:26], room_id=self.room_id, user=dmk_user)
            await asyncio.sleep(1)
            for try_times in range(3):
                r = await send_danmaku(msg=message[26:], room_id=self.room_id, user=dmk_user)
                if r:
                    return
            # logging.info(
            #     f"{self.short_room_id}-{self.name}"
            #     f"\n\t{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}"
            # )

    async def parse_danmaku(self):
        while True:
            dmk = await self.q.get()
            try:
                await self.proc_one_danmaku(dmk)
            except Exception as e:
                if dmk == {"code": 0}:
                    continue

                logging.error(f"Error happened in processing one dmk: {dmk}, e: {e}")

    async def run(self):
        flag, live_status = await BiliApi.get_live_status(room_id=self.room_id)
        if not flag:
            logging.error(f"Cannot get live status when init... e: {live_status}")
        else:
            logging.info(f"Live room status: {self.room_id} -> {live_status}")

            self._is_live = bool(live_status)
            self._last_live_time = time.time()

        await self.parse_danmaku()


class WsManager(object):

    def __init__(self):
        self._clients = {}
        self.monitor_live_rooms = {}

        self.msg_count = 0
        self._broken_live_rooms = []
        self.heartbeat_pkg = WsApi.gen_heart_beat_pkg()

    async def new_room(self, room_id, q):
        client = self._clients.get(room_id)

        if client and not client.set_shutdown:
            return

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                self.msg_count += 1
                q.put_nowait(msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_error(e, msg):
            self._broken_live_rooms.append(room_id)
            logging.error(f"WS ERROR! room_id: [{room_id}], msg: {msg}, e: {e}")

        new_client = RCWebSocketClient(
            url=WsApi.BILI_WS_URI,
            on_message=on_message,
            on_error=on_error,
            on_connect=on_connect,
            heart_beat_pkg=self.heartbeat_pkg,
            heart_beat_interval=10
        )
        new_client.room_id = room_id
        self._clients[room_id] = new_client
        await new_client.start()

    async def kill_client_and_remove_it(self, room_id):
        client = self._clients.get(room_id)

        if client and not client.set_shutdown:
            await client.kill()
            del self._clients[room_id]

    async def run(self):
        self.monitor_live_rooms = expected
        dps = []

        for room_id in expected:
            flag, data = await BiliApi.get_live_room_info_by_room_id(room_id=room_id)
            if flag:
                uid = data["uid"]
                user_name = await BiliApi.get_user_name(uid=uid)
                short_room_id = data["short_id"]
                room_id = data["room_id"]
            else:
                user_name = "??"
                short_room_id = room_id

            q = asyncio.Queue()
            await self.new_room(room_id, q)

            dp = DanmakuProcessor(q=q, room_id=room_id, short_room_id=short_room_id, name=user_name)
            dps.append(asyncio.create_task(dp.run()))

        logging.info(f"Ws monitor settings read finished, Need add: {expected}.")
        for dp_task in dps:
            await dp_task


async def main():
    logging.info("Super sign start...")

    mgr = WsManager()
    await mgr.run()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
