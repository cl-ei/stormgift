import time
import asyncio
import traceback
from utils.ws import RCWebSocketClient
from utils.dao import MonitorLiveRooms
from utils.mq import mq_source_to_raffle
from utils.biliapi import BiliApi, WsApi
from config.log4 import lt_ws_source_logger as logging
from utils.model import objects, MonitorWsClient


class WsManager(object):

    def __init__(self):
        self._clients = {}
        self.monitor_live_rooms = {}

        self.msg_count = 0
        self._broken_live_rooms = []
        self.heartbeat_pkg = WsApi.gen_heart_beat_pkg()

    async def new_room(self, room_id):
        client = self._clients.get(room_id)

        if client and not client.set_shutdown:
            return

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                self.msg_count += 1

                cmd = msg["cmd"]
                if cmd.startswith("DANMU_MSG") and msg["info"][2][0] in (39748080, 65568410):
                    # uid = msg["info"][2][0]
                    logging.info(f"DANMU_MSG: put to mq, room_id: {room_id}, msg: {msg}")
                    await mq_source_to_raffle.put((msg, time.time(), room_id))

                elif cmd in ("GUARD_BUY", "RAFFLE_END", "TV_END", "PK_LOTTERY_START"):
                    r = await mq_source_to_raffle.put((msg, time.time(), room_id))
                    logging.info(f"RECEIVED: {cmd}, put to mq r: {r}, room_id: {room_id}, msg: {msg}")

                elif cmd == "SEND_GIFT" and msg["data"]["giftName"] == "节奏风暴":
                    r = await mq_source_to_raffle.put((msg, time.time(), room_id))
                    logging.info(f"RECEIVED: {cmd}-节奏风暴, put to mq r: {r}, room_id: {room_id}, msg: {msg}")

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

    async def update_connections(self):

        expected = await MonitorLiveRooms.get()
        if not expected:
            logging.error(f"Cannot load monitor live rooms from redis! keep current: {len(self.monitor_live_rooms)}")
            return

        self.monitor_live_rooms = expected
        existed = set(self._clients.keys())

        need_add = expected - existed
        need_del = existed - expected
        logging.info(
            f"Ws monitor settings read finished, Need add: {len(need_add)}, need del: {len(need_del)}."
        )

        count = 0
        for room_id in need_del:
            await self.kill_client_and_remove_it(room_id)

            count += 1
            if count % 300 == 0:
                await asyncio.sleep(1)

        for room_id in need_add:
            await self.new_room(room_id)

            count += 1
            if count % 100 == 0:
                await asyncio.sleep(1)

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
        while True:
            await self.update_connections()
            await asyncio.sleep(60)

    async def run_forever(self):
        try:
            await asyncio.gather(*[
                self.task_print_info(),
                self.task_update_connections(),
            ])
        except Exception as e:
            logging.error(f"Error happened in self_ws_source: {e} {traceback.format_exc()}")


async def main():
    await objects.connect()

    logging.info("LT self_ws_source proc start...")

    mgr = WsManager()
    await mgr.run_forever()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
