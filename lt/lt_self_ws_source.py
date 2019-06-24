import sys
import time
import asyncio
import traceback
from utils.ws import RCWebSocketClient
from utils.biliapi import BiliApi, WsApi
from config.log4 import lt_ws_source_logger as logging

BiliApi.USE_ASYNC_REQUEST_METHOD = True


class WsManager(object):

    def __init__(self, count):
        self.monitor_count = count
        self._clients = {}
        self.monitor_live_rooms = []
        self.monitor_live_rooms_update_time = 0
        self.msg_count = 0
        self.heartbeat_pkg = WsApi.gen_heart_beat_pkg()

    async def on_message(self, room_id, message):
        self.msg_count += 1
        cmd = message.get("cmd")
        if cmd in ("GUARD_BUY", ):
            logging.info(f"cmd: {cmd}, msg: {message}")

    async def new_room(self, room_id):
        client = self._clients.get(room_id)

        if client and not client.set_shutdown:
            return

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                await self.on_message(room_id, msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_shut_down():
            pass

        async def on_error(e, msg):
            logging.error(f"Listener CATCH ERROR: {msg}. e: {e}")

        new_client = RCWebSocketClient(
            url=WsApi.BILI_WS_URI,
            on_message=on_message,
            on_error=on_error,
            on_connect=on_connect,
            on_shut_down=on_shut_down,
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

        self.monitor_live_rooms = room_id_list
        logging.info(f"monitor_live_rooms updated! count: {len(self.monitor_live_rooms)}")
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
        while True:
            if count % 11 == 0:
                speed = self.msg_count / 11
                self.msg_count = 0
                logging.info(f"Message speed: {speed:0.2f} msg/s.")

            if count % 30 == 0:
                valid_client_count = 0
                for room_id, c in self._clients.items():
                    if c.status == "OPEN" and c.set_shutdown is False:
                        valid_client_count += 1
                logging.info(f"Active client count: {valid_client_count}, total: {len(self._clients)}.")

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
            await asyncio.sleep(60 * 5 if r else 45)
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
    try:
        monitor_live_room_count = int(sys.argv[1])
    except (TypeError, ValueError, IndexError):
        monitor_live_room_count = 4000

    logging.info("LT self_ws_source proc start...")

    mgr = WsManager(monitor_live_room_count)
    await mgr.run_forever()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
