import time
import asyncio
import traceback
from utils.ws import RCWebSocketClient
from utils.dao import DXJMonitorLiveRooms
from utils.biliapi import BiliApi, WsApi
from config.log4 import super_dxj_logger as logging


class DanmakuProcessor:
    def __init__(self, q, room_id):
        self.q = q
        self.room_id = room_id

    async def parse_danmaku(self, msg):
        print(f"room_id: {self.room_id}: {msg}")

    async def run(self):
        while True:
            msg = await self.q.get()
            await self.parse_danmaku(msg)


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
