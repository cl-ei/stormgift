import time
import asyncio
import aiohttp
from utils.biliapi import WsApi
# from config.log4 import config_logger
from utils.dao import MonitorLiveRooms
# from utils.model import objects, MonitorWsClient

# logging = config_logger("aio_ws")


async def nop(*args, **kw):
    pass


class WsClient:
    def __init__(self, room_id, on_message, on_close, on_error):
        self.room_id = int(room_id)

        self.on_message = on_message or nop
        self.on_close = on_close or nop
        self.on_error = on_error or nop

        self.task = None
        self.session = None
        self.ws = None

        self.is_closed = False
        self.url = "ws://www.madliar.com:1024/console_wss"
        self.url = "ws://broadcastlv.chat.bilibili.com:2244/sub"
        self.join_package = WsApi.gen_join_room_pkg(room_id=self.room_id)
        self.heart_beat_package = WsApi.gen_heart_beat_pkg()

    async def start(self):
        self.session = aiohttp.ClientSession()

        async def keep_alive(client):
            async with client.session.ws_connect(url=client.url) as ws:
                client.ws = ws

                await ws.send_bytes(client.join_package)
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.ERROR:
                        await client.on_error(msg)
                        return
                    await client.on_message(msg.data, msg.type)

            await client.close()

        self.task = asyncio.create_task(keep_alive(self))
        return self

    async def heart_beat(self):
        await self.ws.send_bytes(self.heart_beat_package)

    async def close(self):
        if self.is_closed:
            print("close a closed client.")
            return

        try:
            self.is_closed = True
            await self.ws.close()
        finally:
            await self.on_close(self)


class Handler:
    def __init__(self):
        self.clients_map = {}
        # {
        #   2516117: {"remove": True, "client": client},
        #   ...
        # }
        self._closed_ws_trigger_q = asyncio.Queue()

    async def on_closed(self, client):
        print(f"room_id crashed: {client.room_id}")
        if self._closed_ws_trigger_q.qsize() > 0:
            return

        if self.clients_map[client.room_id]["remove"] is True:
            return

        self._closed_ws_trigger_q.put_nowait(f"Client closed: {client.room_id}")

    async def heart_beat(self):
        while True:
            start_time = time.time()
            count = 0
            for room_id in self.clients_map:
                client = self.clients_map[room_id].get("client")
                if isinstance(client, WsClient):
                    await client.heart_beat()
                    count += 1

            cost_time = time.time() - start_time
            if cost_time > 25:
                sleep_time = 0
            else:
                sleep_time = 25 - cost_time
            print(f"Heart beat cost: {cost_time:.3f}, sleep_time: {sleep_time:.3f}, proc count: {count}")
            await asyncio.sleep(sleep_time)

    async def update(self):
        for room_id in self.clients_map:
            if not isinstance(self.clients_map[room_id], dict):
                self.clients_map[room_id] = {}

            if self.clients_map[room_id].get("remove") is True:
                client = self.clients_map[room_id].get("client")
                if isinstance(client, WsClient):
                    client.on_error = nop
                    await client.close()
                    self.clients_map[room_id]["client"] = None
            else:
                self.clients_map[room_id]["client"] = client = WsClient(
                    room_id=room_id,
                    on_close=self.on_closed,
                    on_error=nop,
                    on_message=nop,
                )
                await client.start()

    async def update_connections(self):
        while True:
            info = await self._closed_ws_trigger_q.get()
            print(f"update_connections triggered, info: {info}")
            await self.update()

    async def load_target_clients_from_redis(self):
        room_id_list = await MonitorLiveRooms.get()
        for room_id in room_id_list:
            if room_id not in self.clients_map:
                self.clients_map[room_id] = {}

            if self.clients_map[room_id].get("remove") is True:
                self.clients_map[room_id]["remove"] = False

        for room_id in self.clients_map:
            if room_id not in room_id_list:
                self.clients_map[room_id]["remove"] = True

    async def run(self):
        t = asyncio.create_task(self.heart_beat())

        await self.load_target_clients_from_redis()
        print(f"clients_map len: {len(self.clients_map)}")

        self._closed_ws_trigger_q.put_nowait("Startup.")
        await self.update_connections()

        await t


async def main():
    h = Handler()
    await h.run()


asyncio.get_event_loop().run_until_complete(main())