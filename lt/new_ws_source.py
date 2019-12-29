import time
import asyncio
import aiohttp
from utils.biliapi import BiliApi
from utils.biliapi import WsApi
from config.log4 import lt_server_logger as logging


MONITOR_COUNT = 20000
danmaku_q = asyncio.Queue()


class WsClient:
    def __init__(self, room_id):
        self.room_id = room_id
        self.session = None
        self.ws_conn = None
        self.task = None
        self._close_sig_q = asyncio.Queue()
        self._url = WsApi.BILI_WS_URI
        self._join_pkg = WsApi.gen_join_room_pkg(room_id=self.room_id)
        self._hb_pkg = WsApi.gen_heart_beat_pkg()

    async def _listen(self):
        closed_reason_q = asyncio.Queue()
        self.session = session = aiohttp.ClientSession()
        self.ws_conn = ws_conn = await session.ws_connect(url=self._url)
        await ws_conn.send_bytes(self._join_pkg)

        async def wait_close():
            await self._close_sig_q.get()
            closed_reason_q.put_nowait("KILL")

        async def receive_msg():
            while True:
                msg = await ws_conn.receive()
                if msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"Error happened!")
                    return
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    print("By closed.")
                    return
                else:
                    # print(f"Rec: {msg.data}")
                    pass

        async def heart_beat():
            while True:
                await asyncio.sleep(30)
                if not ws_conn.closed:
                    await ws_conn.send_bytes(self._hb_pkg)

        fs = [heart_beat(), receive_msg(), wait_close()]
        await asyncio.wait(fs=fs, return_when=asyncio.FIRST_COMPLETED)

        self.ws_conn = None
        print("closed.")
        if not session.closed:
            await session.close()
        self.session = None
        if closed_reason_q.qsize() > 0:
            return closed_reason_q.get_nowait()
        else:
            return None

    async def _listen_for_ever(self):
        while True:
            closed_reason = await self._listen()
            if closed_reason == "KILL":
                print("Listen forever exit!")
                return

    async def connect(self):
        self.task = asyncio.create_task(self._listen_for_ever())

    async def close(self):
        self._close_sig_q.put_nowait("KILL")
        if self.task is not None:
            await self.task
            self.task = None


async def main():
    monitor = []
    flag, data = await BiliApi.get_lived_room_id_by_page(page=1, page_size=400, timeout=30)
    if not flag:
        return
    monitor.extend(data)

    print(len(monitor))
    s_dict = {}

    for i, room_id in enumerate(monitor):
        t = WsClient(room_id=room_id)
        await t.connect()
        s_dict[room_id] = t
        print(f"{i} -> {room_id}, {t}")

    print(f"t.connected! {12}")
    while True:
        await asyncio.sleep(10)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
