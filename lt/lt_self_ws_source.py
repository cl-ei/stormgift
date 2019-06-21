import asyncio
import requests
from utils.dao import redis_cache
from utils.ws import RCWebSocketClient
from utils.biliapi import BiliApi, WsApi
from config.log4 import lt_source_logger as logging
from config import LT_RAFFLE_ID_GETTER_HOST, LT_RAFFLE_ID_GETTER_PORT


VALUABLE_LIVE_ROOM_ID_LIST_KEY = "VALUABLE_LIVE_ROOM_ID_LIST_KEY"


class WsManager(object):

    def __init__(self, count):
        self.monitor_count = count
        self._clients = {}
        self.monitor_live_rooms = []
        self.msg_count = 0
        self.post_prize_url = f"http://{LT_RAFFLE_ID_GETTER_HOST}:{LT_RAFFLE_ID_GETTER_PORT}"
        self.heartbeat_pkg = WsApi.gen_heart_beat_pkg()
        logging.info(f"post_prize_url: {self.post_prize_url}")

    def post_prize_info(self, room_id):
        params = {
            "action": "prize_notice",
            "key_type": "T",
            "room_id": room_id
        }
        try:
            r = requests.get(url=self.post_prize_url, params=params, timeout=0.5)
        except Exception as e:
            error_message = F"Http request error. room_id: {room_id}, e: {str(e)[:20]} ..."
            logging.error(error_message, exc_info=False)
            return

        if r.status_code != 200 or "OK" not in r.content.decode("utf-8"):
            logging.error(
                F"Prize room post failed. code: {r.status_code}, "
                F"response: {r.content}. key: T${room_id}"
            )
            return

        logging.info(f"TV Prize room post success: {room_id}")

    async def on_message(self, room_id, message):
        self.msg_count += 1
        cmd = message.get("cmd")
        # print(f"cmd: {cmd}, msg: {message}")

    async def new_room(self, room_id):
        client = self._clients.get(room_id)

        if client and client.set_shutdown is not True:
            return

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                await self.on_message(room_id, msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_shut_down():
            logging.warning(f"Client shutdown! room_id: {room_id}")

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

    async def kill_room(self, room_id):
        client = self._clients.get(room_id)

        if client and client.set_shutdown is not True:
            await client.kill()
            del self._clients[room_id]

        logging.info(f"WS client killed, room_id: {room_id}")

    async def flush_monitor_live_rooms(self):
        flag, total = await BiliApi.get_all_lived_room_count()
        if not flag:
            print(f"Cannot get lived room count. msg: {total}")
            return

        flag, room_id_list = await BiliApi.get_lived_room_id_list(count=min(total, self.monitor_count))
        if not flag:
            print(f"Cannot get lived rooms. msg: {room_id_list}")
            return

        self.monitor_live_rooms = room_id_list
        print(f"monitor_live_rooms updated! count: {len(self.monitor_live_rooms)}")

    async def update_connections(self):
        existed = set(self._clients.keys())
        expected = set(self.monitor_live_rooms)
        need_add = expected - existed
        need_del = existed - expected
        print(f"Need add room count: {len(need_add)}, need del: {len(need_del)}")

        count = 0
        for room_id in need_del:
            await self.kill_room(room_id)
            del self._clients[room_id]

            count += 1
            if count % 100 == 0:
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
            if count % 5 == 0:
                speed = self.msg_count / 5
                self.msg_count = 0
                print(f"Message speed: {speed:0.2f}")

            if count % 30 == 0:
                valid_client_count = 0
                for room_id, c in self._clients.items():
                    if c.status == "OPEN" and c.set_shutdown is False:
                        valid_client_count += 1
                print(f"Active client count: {valid_client_count}, total: {len(self._clients)}.")

            count += 1
            if count > 1000000000:
                count = 0

            await asyncio.sleep(1)

    async def task_update_connections(self):
        while True:
            await self.update_connections()
            await asyncio.sleep(60)

    async def task_flush_monitor_live_rooms(self):
        while True:
            await asyncio.sleep(60 * 5)
            await self.flush_monitor_live_rooms()

    async def run_forever(self):
        await self.flush_monitor_live_rooms()

        p = asyncio.create_task(self.task_print_info())
        f = asyncio.create_task(self.task_update_connections())
        u = asyncio.create_task(self.task_flush_monitor_live_rooms())

        await p
        await u
        await f


async def main():
    logging.info("LT self_ws_source proc start...")
    monitor_live_room_count = 20000
    mgr = WsManager(monitor_live_room_count)
    await mgr.run_forever()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
