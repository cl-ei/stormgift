import time
import asyncio
import traceback
from utils.ws import RCWebSocketClient
from utils.dao import DXJMonitorLiveRooms, SuperDxjUserSettings
from utils.biliapi import BiliApi, WsApi
from config.log4 import super_dxj_logger as logging


class DanmakuProcessor:
    def __init__(self, q, room_id):
        self.q = q
        self.room_id = room_id
        self._settings_load_time = 0
        self._cached_settings = None
        self._last_settings_version = None
        self.last_dmk_active_time = 0

    async def send_danmaku(self, message):
        logging.info(f"Send dmk: {message}")

    async def load_config(self):
        if int(time.time()) - self._settings_load_time < 60 and self._cached_settings:
            return self._cached_settings

        self._cached_settings = await SuperDxjUserSettings.get(room_id=self.room_id)
        self._settings_load_time = time.time()
        self._last_settings_version = self._cached_settings["last_update_time"]
        return self._cached_settings

    @property
    def is_live(self):
        settings = await self.load_config()
        if time.time() - self.last_dmk_active_time < settings["carousel_msg_interval"]:
            return True
        else:
            return False

    async def proc_one_danmaku(self, dmk):
        settings = await self.load_config()
        cmd = dmk["cmd"]
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
            logging.info(f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}")

            if msg in settings["carousel_msg"]:
                return

            self.last_dmk_active_time = int(time.time())

            for key_word, text in settings["auto_response"]:
                if key_word in msg:
                    return await self.send_danmaku(text)

        elif cmd == "GUARD_BUY":
            data = dmk.get("data")
            uid = data.get("uid")
            uname = data.get("username", "")
            gift_name = data.get("gift_name", "GUARD")
            price = data.get("price", 0)
            num = data.get("num", 0)
            created_time = data.get("start_time", 0)

            logging.info(f"GUARD_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (price: {price})")
            thank_gold = settings["thank_gold"]
            if thank_gold == 1 or (thank_gold == 2 and not self.is_live) or (thank_gold == 3 and self.is_live):
                thank_gold_text = settings["thank_gold_text"].replace(
                    "{num}", str(num)
                ).replace(
                    "{gift}", gift_name
                ).replace(
                    "{user}", uname
                )
                await self.send_danmaku(thank_gold_text)

        else:
            print(f"room_id: {self.room_id}: {dmk}")

    async def parse_danmaku(self):
        while True:
            dmk = await self.q.get()
            try:
                await self.proc_one_danmaku(dmk)
            except Exception as e:
                logging.error(f"Error happened in processing one dmk: {dmk}, e: {e}")

    async def send_carousel_msg(self):
        while True:
            await asyncio.sleep(10)

    async def run(self):
        await asyncio.gather(*[
            self.parse_danmaku(),
            self.send_carousel_msg(),
        ])


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
        expected = await DXJMonitorLiveRooms.get()
        if not expected:
            logging.error(f"Cannot load monitor live rooms from redis!")
            return

        self.monitor_live_rooms = expected

        logging.info(
            f"Ws monitor settings read finished, Need add: {expected}."
        )
        dps = []
        for room_id in expected:
            q = asyncio.Queue()
            await self.new_room(room_id, q)

            dp = DanmakuProcessor(q=q, room_id=room_id)
            dps.append(asyncio.create_task(dp.run()))

        for dp_task in dps:
            await dp_task


async def main():
    logging.info("Super dxj start...")

    mgr = WsManager()
    await mgr.run()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
