import sys
import time
import asyncio
import traceback
from utils.ws import RCWebSocketClient, get_ws_established_and_time_wait
from utils.biliapi import BiliApi, WsApi
from utils.dao import ValuableLiveRoom
from config.log4 import lt_ws_source_logger as logging
from lt import LtGiftMessageQ
from utils.model import objects, MonitorWsClient


BiliApi.USE_ASYNC_REQUEST_METHOD = True


class WsManager(object):

    def __init__(self, count):
        self.monitor_count = count
        self._clients = {}
        self.monitor_live_rooms = []
        self.monitor_live_rooms_update_time = 0

        self.msg_count = 0
        self._broken_live_rooms = []
        self.heartbeat_pkg = WsApi.gen_heart_beat_pkg()

    async def on_message(self, room_id, message):
        self.msg_count += 1
        if message["cmd"] == "GUARD_BUY" and message["data"]["guard_level"] != 1:
            logging.info(f"cmd: {message['cmd']}, room_id: {room_id}, msg: {message}")
            await LtGiftMessageQ.post_gift_info("G", room_id)

    async def new_room(self, room_id):
        client = self._clients.get(room_id)

        if client and not client.set_shutdown:
            return

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                await self.on_message(room_id, msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_error(e, msg):
            self._broken_live_rooms.append(room_id)
            # logging.error(f"WS ERROR! room_id: [{room_id}], msg: {msg}, e: {e}")

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

    async def flush_monitor_live_room_list(self):
        flag, total = await BiliApi.get_all_lived_room_count()
        if not flag:
            logging.error(f"Cannot get lived room count. msg: {total}")
            return False

        await asyncio.sleep(1)

        flag, room_id_list = await BiliApi.get_lived_room_id_list(count=min(total, self.monitor_count))
        if not flag:
            logging.error(f"Cannot get lived rooms. msg: {room_id_list}")
            return False

        valuable_room_count_limit = 3000
        valuable_live_rooms = await ValuableLiveRoom.get_all()
        valuable_count = len(valuable_live_rooms)
        if valuable_count > valuable_room_count_limit:
            logging.error(
                f"TOO MANY Valuable live rooms! count: {valuable_count}, "
                f"now only fetch top {valuable_room_count_limit}."
            )
            valuable_live_rooms = valuable_live_rooms[:valuable_room_count_limit]
            valuable_count = len(valuable_live_rooms)

        api_count = len(room_id_list)
        self.monitor_live_rooms = list(set(room_id_list + valuable_live_rooms))
        total_count = len(self.monitor_live_rooms)
        cache_hit_rate = 100 * (api_count + valuable_count - total_count) / valuable_count

        logging.info(
            f"monitor_live_rooms updated! api count: {api_count}, valuable: {valuable_count}, "
            f"total: {total_count}, cache_hit_rate: {cache_hit_rate:.1f}%"
        )

        established, time_wait = get_ws_established_and_time_wait()
        __monitor_info = {
            "valuable room": valuable_count,
            "api room cnt": api_count,
            "target clients": total_count,
            "valuable hit rate": cache_hit_rate,
            "TCP ESTABLISHED": established,
            "TCP TIME_WAIT": time_wait,
        }
        await MonitorWsClient.record(__monitor_info)

        self.monitor_live_rooms_update_time = time.time()
        return True

    async def update_connections(self):

        existed = set(self._clients.keys())
        expected = set(self.monitor_live_rooms)
        need_add = expected - existed
        need_del = existed - expected

        logging.info(f"Need add room count: {len(need_add)}, need del: {len(need_del)}")

        count = 0
        for room_id in need_del:
            await self.kill_client_and_remove_it(room_id)

            count += 1
            if count % 300 == 0:
                await asyncio.sleep(1)

            if count > 999999999:
                count = 0

        for room_id in need_add:
            await self.new_room(room_id)

            count += 1
            if count % 100 == 0:
                await asyncio.sleep(1)

            if count > 999999999:
                count = 0

    async def task_print_info(self):
        count = 0
        msg_count_of_last_second = 0
        msg_speed_peak = 0
        while True:

            msg_speed_peak = max(self.msg_count - msg_count_of_last_second, msg_speed_peak)
            msg_count_of_last_second = self.msg_count

            if count % 11 == 0:
                speed = self.msg_count / 11

                if self._broken_live_rooms:
                    append_msg = (
                        f"broken count: {len(self._broken_live_rooms)}, "
                        f"{','.join([str(r) for r in self._broken_live_rooms[:10]])}"
                        f"{' ...' if len(self._broken_live_rooms) > 10 else '.'}"
                    )
                else:
                    append_msg = ""

                logging.info(f"Message speed avg: {speed:0.2f}, peak: {msg_speed_peak}. {append_msg}")
                __monitor_info = {
                    "msg speed": speed,
                    "msg peak speed": msg_speed_peak,
                    "broken clients": len(self._broken_live_rooms)
                }
                await MonitorWsClient.record(__monitor_info)

                self.msg_count = 0
                self._broken_live_rooms = []
                msg_count_of_last_second = 0
                msg_speed_peak = 0

            if count % 30 == 0:
                total = len(self._clients)
                valid_client_count = 0
                for room_id, c in self._clients.items():
                    if c.status == "OPEN" and c.set_shutdown is False:
                        valid_client_count += 1

                logging.info(f"Active client count: {valid_client_count}, total: {total}.")
                await MonitorWsClient.record({"active clients": valid_client_count, "total clients": total})

            count += 1
            if count > 1000000000:
                count = 0

            await asyncio.sleep(1)

    async def task_update_connections(self):
        update_connection_timestamp = 0
        while True:
            if update_connection_timestamp == self.monitor_live_rooms_update_time:
                await asyncio.sleep(1)

            else:
                update_connection_timestamp = self.monitor_live_rooms_update_time
                await self.update_connections()

    async def task_flush_monitor_live_rooms(self):
        r = True
        while True:
            await asyncio.sleep(60 * 5 if r else 120)
            r = await self.flush_monitor_live_room_list()

    async def run_forever(self):
        await self.flush_monitor_live_room_list()

        try:
            await asyncio.gather(*[
                self.task_print_info(),
                self.task_update_connections(),
                self.task_flush_monitor_live_rooms(),
            ])
        except Exception as e:
            logging.error(f"Error happened in self_ws_source: {e} {traceback.format_exc()}")


async def main():
    await objects.connect()

    try:
        monitor_live_room_count = int(sys.argv[1])
    except (TypeError, ValueError, IndexError):
        monitor_live_room_count = 4000

    logging.info("LT self_ws_source proc start...")

    mgr = WsManager(monitor_live_room_count)
    await mgr.run_forever()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
