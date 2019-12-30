import sys
import time
import asyncio
import aiohttp
from utils.biliapi import WsApi
from config.log4 import lt_server_logger as logging
from utils.dao import MonitorLiveRooms, InLotteryLiveRooms, ValuableLiveRoom
# from utils.model import MonitorWsClient

MONITOR_COUNT = 1000
DEBUG = True

if sys.argv[-1].lower() == "--product":
    logging.setLevel("INFO")
    DEBUG = False


class WsClient:
    def __init__(self, room_id, on_message, on_broken):
        self.room_id = room_id

        self.on_message = on_message
        self.on_broken = on_broken

        self.session = None
        self.task = None
        self._close_sig_q = asyncio.Queue()
        self._url = WsApi.BILI_WS_URI
        self._join_pkg = WsApi.gen_join_room_pkg(room_id=self.room_id)
        self._hb_pkg = WsApi.gen_heart_beat_pkg()

        self._connect_times = 0
        self._reconnect_time = 0

    async def _listen(self):
        self.session = session = aiohttp.ClientSession()
        ws_conn = await session.ws_connect(url=self._url)
        await ws_conn.send_bytes(self._join_pkg)

        self._connect_times += 1
        self._reconnect_time = 0

        async def wait_close(q):
            await q.get()
            return "KILL"

        async def receive_msg():
            while True:
                try:
                    msg = await ws_conn.receive()
                except Exception as e:
                    logging.error(f"Error happened in ws receive msg: {e}")
                    return f"ERROR: {e}"

                if msg.type == aiohttp.WSMsgType.ERROR:
                    return f"ERROR: {msg.data}"
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    return f"CLOSED_BY_REMOTE"
                else:
                    await self.on_message(msg.data, self)

        async def heart_beat():
            while True:
                await asyncio.sleep(50)
                if not ws_conn.closed:
                    await ws_conn.send_bytes(self._hb_pkg)

        fs = [heart_beat(), receive_msg(), wait_close(self._close_sig_q)]
        done, pending = await asyncio.wait(fs=fs, return_when=asyncio.FIRST_COMPLETED)

        closed_reason = None
        for done_task in done:
            closed_reason = done_task.result()
            break
        return closed_reason

    async def _listen_for_ever(self):
        while True:
            try:
                closed_reason = await self._listen()
            except Exception as e:
                logging.warning(f"WS._listen raised a Exception! {e}")
                closed_reason = F"EXCEPTION: {e}"

            if self.session and not self.session.closed:
                await self.session.close()
                self.session = None

            if closed_reason == "KILL":
                return
            else:
                await self.on_broken(closed_reason, self)
                logging.debug(F"_listen BROKEN: {self.room_id}, reason: {closed_reason}")
            self._reconnect_time += 1

            sleep_time = min(self._reconnect_time / 5, 2)
            await asyncio.sleep(sleep_time)

    async def connect(self):
        if self.task is not None:
            if self.task.done():
                logging.error(f"Task shutdown! {self.room_id} -> {self.task}")
                raise RuntimeError("Monitor Task shutdown!")
            else:
                logging.warning(f"Task ALREADY Created! {self.task}")
                return

        self.task = asyncio.create_task(self._listen_for_ever())

    async def close(self):
        if self.task is None:
            logging.warning(f"Monitor Task pending! {self.room_id}")
            return

        if self.task.done():
            logging.error(f"Task ALREADY closed! {self.room_id} -> {self.task}")
            raise RuntimeError("Task ALREADY closed!")

        self._close_sig_q.put_nowait("KILL")
        await self.task


class ClientsManager:
    def __init__(self):
        self._all_clients = set()
        self._message_q = asyncio.Queue()
        self._message_count = 0
        self._broken_clients = asyncio.Queue()

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

            logging.debug(f"Monitor rooms get from redis: {len(expected)}")

            existed = {ws.room_id for ws in self._all_clients}
            need_add = expected - existed
            need_del = existed - expected

            if len(need_del) > 0 or len(need_add) > 0:
                log = f"WS MONITOR CLIENTS UPDATE: need add {len(need_add)}, del: {len(need_del)}"
                if 0 < len(need_add):
                    log += f"\n\tadd: {list(need_add)[:10]}{'...' if len(need_add) > 10 else ''}"
                if 0 < len(need_del):
                    log += f"\n\tdel: {list(need_del)[:10]}{'...' if len(need_del) > 10 else ''}"
                logging.info(log)

            need_del_clients = {ws for ws in self._all_clients if ws.room_id in need_del}
            for ws in need_del_clients:
                await ws.close()
                self._all_clients.remove(ws)

            for i, room_id in enumerate(need_add):
                if i > 0 and i % 300 == 0:
                    await asyncio.sleep(1)

                async def on_message(msg, ws):
                    self._message_count += 1
                    self._message_q.put_nowait((time.time(), ws.room_id, msg))

                async def on_broken(reason, ws):
                    self._broken_clients.put_nowait(f"{ws.room_id}${reason}")

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
            # await MonitorWsClient.record(__monitor_info)

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

                active_clients = 0
                monitor_rooms = set()
                for i, ws in enumerate(self._all_clients):
                    monitor_rooms.add(ws.room_id)
                    if ws.task and not ws.task.done():
                        active_clients += 1
                    else:
                        logging.debug(
                            f"\ti: {i} -> {ws.room_id}: task: {ws.task}, conn: {ws.ws_conn}, session: {ws.session}")

                broken_times = self._broken_clients.qsize()
                log += (
                    f"Clients {active_clients}/{len(self._all_clients)}, all rooms: {len(monitor_rooms)}, "
                    f"broken_times: {broken_times}"
                )

                broken_details = {}
                broken_count = 0
                for _ in range(broken_times):
                    room_id, reason = self._broken_clients.get_nowait().split("$", 1)
                    broken_details.setdefault(reason, []).append(room_id)
                for reason, rooms in broken_details.items():
                    broken_count += len(rooms)
                    de_dup_rooms = set(rooms)
                    if DEBUG or len(rooms) > 50:
                        log += f"\n\t{reason} {len(de_dup_rooms)} rooms broken {len(rooms)} times."

                logging.info(log)

                __monitor_info = {
                    "msg speed": msg_speed_avg,
                    "msg peak speed": msg_speed_peak,
                    "broken clients": broken_count
                }
                # await MonitorWsClient.record(__monitor_info)

                self._message_count = 0
                msg_speed_peak = 0

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
