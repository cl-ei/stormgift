import sys
import time
import asyncio
import aiohttp
import traceback
from random import randint
from utils.biliapi import WsApi
from utils.udp import mq_source_to_raffle
from multiprocessing import Process, Queue
from config.log4 import lt_server_logger as logging
from utils.dao import MonitorLiveRooms, InLotteryLiveRooms, ValuableLiveRoom
from utils.model import objects, MonitorWsClient


DEBUG = True
MONITOR_COUNT = 20000
parse_process = None


if sys.argv[-1].lower() == "--product":
    logging.setLevel("INFO")
    DEBUG = False


def danmaku_parser_process(damaku_q):

    def parse(ts, room_id, msg):
        cmd = msg["cmd"]
        if cmd == "GUARD_LOTTERY_START":
            mq_source_to_raffle.put_nowait(("G", room_id, msg, ts))
            logging.info(f"SOURCE: {cmd}, room_id: {room_id}")

        elif cmd == "SPECIAL_GIFT":
            mq_source_to_raffle.put_nowait(("S", room_id, msg, ts))
            logging.info(f"SOURCE: {cmd}-节奏风暴, room_id: {room_id}")

        elif cmd == "PK_LOTTERY_START":
            mq_source_to_raffle.put_nowait(("P", room_id, msg, ts))
            logging.info(f"SOURCE: {cmd}, room_id: {room_id}")

        elif cmd in ("RAFFLE_END", "TV_END", "ANCHOR_LOT_AWARD"):
            mq_source_to_raffle.put_nowait(("R", room_id, msg, ts))
            display_msg = msg.get("data", {}).get("win", {}).get("msg", "")
            logging.info(f"SOURCE: {cmd}, room_id: {room_id}, msg: {display_msg}")

        elif cmd.startswith("DANMU_MSG"):
            if msg["info"][2][0] in (
                64782616,  # 温柔桢
                9859414,   # G7
            ):
                mq_source_to_raffle.put_nowait(("D", room_id, msg, ts))
                logging.info(f"DANMU_MSG: put to mq, room_id: {room_id}, msg: {msg}")

        elif cmd == "ANCHOR_LOT_START":
            mq_source_to_raffle.put_nowait(("A", room_id, msg, ts))
            data = msg["data"]
            logging.info(f"SOURCE: {cmd}, room_id: {room_id}, {data['require_text']} -> {data['award_name']}")

        elif cmd == "RAFFLE_START":
            data = msg["data"]
            mq_source_to_raffle.put_nowait(("RAFFLE_START", room_id, msg, ts))
            logging.info(f"SOURCE: {cmd}, room_id: {room_id}, {data['thank_text']}")

    while True:
        start_time, msg_from_room_id, danmaku = damaku_q.get()
        for m in WsApi.parse_msg(danmaku):
            try:
                parse(start_time, msg_from_room_id, m)
            except KeyError:
                continue
            except Exception as e:
                logging.error(f"Error Happened in parse danmaku: {e}\n{traceback.format_exc()}")
                continue


class WsClient:
    def __init__(self, room_id, on_message, on_broken):
        self.room_id = room_id
        self.on_message = on_message
        self.on_broken = on_broken

        self.session = None
        self.task = None
        self.task_heartbeat = None
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

        async def heart_beat():
            while True:
                await asyncio.sleep(50)
                if not ws_conn.closed:
                    await ws_conn.send_bytes(self._hb_pkg)

        if self.task_heartbeat is not None:
            raise RuntimeError(f"self.task_heartbeat task not stopped! It will caused MEMORY_LEAK!")
        self.task_heartbeat = asyncio.create_task(heart_beat())

        while True:
            msg = await ws_conn.receive()
            if msg.type == aiohttp.WSMsgType.ERROR:
                closed_reason = f"ERROR: {msg.data}"
                break
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                closed_reason = f"CLOSED_BY_REMOTE"
                break
            else:
                await self.on_message(msg.data, self)

        return closed_reason

    async def _listen_for_ever(self):
        while True:
            try:
                closed_reason = await self._listen()
            except asyncio.CancelledError:
                closed_reason = "KILL"
            except Exception as e:
                logging.warning(f"WS._listen raised a Exception! {e}")
                closed_reason = F"EXCEPTION: {e}"

            if self.session and not self.session.closed:
                await self.session.close()
                self.session = None

            if self.task_heartbeat:
                if self.task_heartbeat.done():
                    raise RuntimeError("self.task_heartbeat Should not be done!")
                self.task_heartbeat.cancel()
                self.task_heartbeat = None

            if closed_reason == "KILL":
                return

            await self.on_broken(closed_reason, self)
            logging.debug(F"_listen BROKEN: {self.room_id}, reason: {closed_reason}")

            self._reconnect_time += 1
            if self._reconnect_time < 3:
                sleep_time = randint(200, 1000) / 1000
            elif self._reconnect_time < 10:
                sleep_time = randint(1000, 5000) / 1000
            else:
                sleep_time = randint(5000, 15000) / 1000
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

        self.task.cancel()
        self.task = None


class ClientsManager:
    def __init__(self, q):
        self._all_clients = set()
        self._message_q = q
        self._message_count = 0
        self._broken_clients = asyncio.Queue()

    async def update_connection(self):

        async def run_once():
            start_time = time.time()
            logging.info(f"WS MONITOR CLIENTS UPDATING...start: {start_time}.")

            in_lottery = await InLotteryLiveRooms.get_all()
            expected = in_lottery | (await MonitorLiveRooms.get())
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
            logging.info(f"WS MONITOR CLIENTS UPDATING: close non-active clients, count: {len(need_del_clients)}")
            for ws in need_del_clients:
                await ws.close()
                self._all_clients.remove(ws)

            logging.info(f"WS MONITOR CLIENTS CREATING NEW: {len(need_add)}")
            for i, room_id in enumerate(need_add):
                if i > 0 and i % 300 == 0:
                    await asyncio.sleep(1)

                async def on_broken(reason, ws):
                    self._broken_clients.put_nowait(f"{ws.room_id}${reason}")

                async def on_message(data, ws):
                    self._message_count += 1
                    m = (int(time.time()), ws.room_id, data)
                    self._message_q.put_nowait(m)

                ws = WsClient(
                    room_id=room_id,
                    on_message=on_message,
                    on_broken=on_broken,
                )
                await ws.connect()
                self._all_clients.add(ws)
            logging.info(f"WS MONITOR CLIENTS UPDATING: MonitorWsClient.")
            # record
            __monitor_info = {
                "valuable room": len(valuable),
                "target clients": len(expected),
                "valuable hit rate": cache_hit_rate,
            }
            await MonitorWsClient.record(__monitor_info)

            logging.info(
                f"WS MONITOR CLIENTS UPDATE! cost: {time.time() - start_time:.3f}."
                f"\n\tadd {len(need_add)}: {list(need_add)[:10]}"
                f"\n\tdel {len(need_del)}: {list(need_del)[:10]}"
                f"\n\texpected: {len(expected)}, in lottery {len(in_lottery)}, valuable: {len(valuable)}"
            )

        while True:
            await run_once()
            await asyncio.sleep(60)

    async def monitor_status(self):
        msg_speed_peak = 0
        msg_count_of_last_second = 0

        cyc_count = 0
        cyc_duration = 59
        while True:
            start_time = time.time()
            p_status = parse_process.is_alive() if parse_process else '-'
            if p_status is False:
                logging.error(f"Sub process: Parse danmaku process unexpected shutdown! now exit.")
                sys.exit(-1)

            msg_speed_peak = max(self._message_count - msg_count_of_last_second, msg_speed_peak)
            msg_count_of_last_second = self._message_count

            if cyc_count % cyc_duration == 0:
                msg_speed_avg = self._message_count / cyc_duration
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
                    log += f"\n\t{reason} {len(de_dup_rooms)} rooms broken {len(rooms)} times."

                logging.info(log)

                __monitor_info = {
                    "msg speed": msg_speed_avg,
                    "msg peak speed": msg_speed_peak,
                    "broken clients": broken_count,
                    "active clients": active_clients,
                    "total clients": len(self._all_clients)
                }
                await MonitorWsClient.record(__monitor_info)
                self._message_count = 0
                msg_speed_peak = 0

            cost = time.time() - start_time
            await asyncio.sleep(max(0.0, 1 - cost))
            cyc_count += 1

    async def run(self):
        try:
            await asyncio.gather(
                self.update_connection(),
                self.monitor_status(),
            )
        except Exception as e:
            logging.error(f"WS MONITOR EXIT! Exception: {e}\n\n{traceback.format_exc()}")


def main():
    global parse_process

    danmaku_q = Queue()
    parse_process = Process(target=danmaku_parser_process, args=(danmaku_q, ), daemon=False)
    parse_process.start()

    async def run():
        await objects.connect()
        mgr = ClientsManager(danmaku_q)
        await mgr.run()
        await objects.close()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())


if __name__ == "__main__":
    main()
