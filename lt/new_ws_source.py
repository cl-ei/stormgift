import time
import asyncio
import aiohttp
from utils.biliapi import WsApi
from config.log4 import lt_server_logger as logging
from utils.dao import MonitorLiveRooms, InLotteryLiveRooms, ValuableLiveRoom
from utils.model import MonitorWsClient
MONITOR_COUNT = 20000


class WsClient:
    def __init__(self, room_id, on_message, on_broken):
        self.room_id = room_id

        self.on_message = on_message
        self.on_broken = on_broken

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
            if closed_reason_q.qsize() == 0:
                closed_reason_q.put_nowait("KILL")

        async def receive_msg():
            while True:
                msg = await ws_conn.receive()
                if msg.type == aiohttp.WSMsgType.ERROR:
                    closed_reason_q.put_nowait(f"ERROR: {msg.data}")
                    return
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    closed_reason_q.put_nowait(f"CLOSED: {msg.data}")
                    return
                else:
                    await self.on_message(msg)

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

        closed_reason = None
        if closed_reason_q.qsize() > 0:
            closed_reason = closed_reason_q.get_nowait()
        if closed_reason != "KILL":
            await self.on_broken(closed_reason)
        return closed_reason

    async def _listen_for_ever(self):
        while True:
            closed_reason = await self._listen()
            if closed_reason == "KILL":
                print("Listen forever exit!")
                return
            else:
                print(f"Closed reason: {closed_reason}")

    async def connect(self):
        if self.task and not self.task.done():
            logging.warning("Task ALREADY running!")
            return

        self.task = asyncio.create_task(self._listen_for_ever())

    async def close(self):
        if self.task is None or self.task.done():
            logging.warning("Task ALREADY closed!")
            return

        self._close_sig_q.put_nowait("KILL")
        await self.task
        self.task = None


class ClientsManager:
    def __init__(self):
        self._all_clients = set()
        self._message_q = asyncio.Queue()
        self._message_count = 0
        self._broken_clients = {}

    async def update_connection(self):
        cyc_time = 60
        while True:
            start_time = time.time()

            expected = await MonitorLiveRooms.get()
            in_lottery = await InLotteryLiveRooms.get_all()
            expected |= in_lottery
            valuable = await ValuableLiveRoom.get_all()
            valuable_hit_count = 0
            for room_id in valuable:
                expected_len = len(expected)
                if expected_len >= MONITOR_COUNT:
                    break
                expected.add(room_id)
                if len(expected) == expected_len:
                    valuable_hit_count += 1
            cache_hit_rate = valuable_hit_count / len(valuable) * 100

            existed = {ws.room_id for ws in self._all_clients}
            need_add = expected - existed
            need_del = existed - expected

            need_del_clients = {ws for ws in self._all_clients if ws.room_id in need_del}
            for ws in need_del_clients:
                await ws.close()
                self._all_clients.remove(ws)

            for room_id in need_add:

                async def on_message(msg):
                    self._message_count += 1
                    self._message_q.put_nowait((time.time(), room_id, msg))

                async def on_broken(reason):
                    self._broken_clients.setdefault(reason, []).append(room_id)

                ws = WsClient(
                    room_id=room_id,
                    on_message=on_message,
                    on_broken=on_broken,
                )
                await ws.connect()
                self._all_clients.add(ws)

            # record
            __monitor_info = {
                "valuable room": len(valuable),
                "target clients": len(expected),
                "valuable hit rate": cache_hit_rate,
            }
            await MonitorWsClient.record(__monitor_info)

            cost = time.time() - start_time
            if cost < cyc_time:
                await asyncio.sleep(cyc_time - cost)

    async def parse_message(self):
        async def parse_one(ts, room_id, msg):
            pass

        while True:
            ts, room_id, raw = await self._message_q.get()
            for m in WsApi.parse_msg(raw):
                try:
                    await parse_one(ts, room_id, m)
                except Exception as e:
                    logging.error(f"PARSE_MSG_ERROR: {e}")

    async def monitor_status(self):
        msg_speed_peak = 0
        msg_count_of_last_second = 0

        cyc_count = 0
        while True:
            start_time = time.time()

            msg_speed_peak = max(self._message_count - msg_count_of_last_second, msg_speed_peak)
            msg_count_of_last_second = self._message_count

            if cyc_count % 31 == 0:
                msg_speed_avg = self._message_count / 31

                log = f"Message speed avg: {msg_speed_avg:0.2f}, peak: {msg_speed_peak}. "

                clients_broken_detail = self._broken_clients
                self._broken_clients = {}

                broken_count = 0
                for reason, rooms in clients_broken_detail.items():
                    de_dup_rooms = set(rooms)
                    broken_count += len(de_dup_rooms)
                    if len(rooms) > 50:
                        log += f"\n {reason} broken times: {len(rooms)}, rooms: {len(de_dup_rooms)}"

                logging.info(log)

                __monitor_info = {
                    "msg speed": msg_speed_avg,
                    "msg peak speed": msg_speed_peak,
                    "broken clients": broken_count
                }
                await MonitorWsClient.record(__monitor_info)

            cost = time.time() - start_time
            if cost < 1:
                await asyncio.sleep(1 - cost)
            else:
                logging.warning("")
            cyc_count += 1

    async def run(self):
        fs = [
            self.parse_message(),
            self.update_connection(),
            self.monitor_status(),
        ]
        done, pending = await asyncio.wait(fs=fs, return_when=asyncio.FIRST_COMPLETED)
        logging.error(f"WS MONITOR EXIT! done: {done}, pending: {pending}")


async def main():
    mgr = ClientsManager()
    await mgr.run()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
