import asyncio
from random import random
from lt import LtGiftMessageQ
from utils.ws import RCWebSocketClient
from utils.biliapi import BiliApi, WsApi
from config.log4 import lt_source_logger as logging

BiliApi.USE_ASYNC_REQUEST_METHOD = True


class TvScanner(object):
    AREA_MAP = {
        0: "全区",
        1: "娱乐",
        2: "网游",
        3: "手游",
        4: "绘画",
        5: "电台",
        6: "单机",
    }

    def __init__(self):
        self.__rws_clients = {}
        self.__lock_when_changing_room = {}  # {1: [old_room_id, call by], ...}

    async def on_message(self, area_id, room_id, message):
        area_name = self.AREA_MAP[area_id]

        cmd = message.get("cmd")
        if cmd == "PREPARING":
            logging.warning(f"Room {room_id} from area {area_name} closed! now search new.")
            await self.force_change_room(old_room_id=room_id, area_id=area_id, call_by="on_message")

        elif cmd == "NOTICE_MSG":
            msg_self = message.get("msg_self", "")
            matched_notice_area = False
            if area_id == 1 and msg_self.startswith("全区"):
                matched_notice_area = True
            elif msg_self.startswith(area_name):
                matched_notice_area = True

            if matched_notice_area:
                real_room_id = message.get("real_roomid", 0)
                logging.info(
                    f"PRIZE: [{msg_self[:2]}] room_id: {real_room_id}, msg: {msg_self}. "
                    f"source: {area_id}-{area_name}-{room_id}"
                )
                await LtGiftMessageQ.post_gift_info("T", real_room_id)

    async def force_change_room(self, old_room_id, area_id, call_by):
        # 检查锁并加锁
        change_info = self.__lock_when_changing_room.get(area_id)
        area_name = self.AREA_MAP[area_id]

        if change_info:
            sign = str(random())
            old_room_id, old_call_by = change_info

            logging.error(
                f"\n{'-' * 80}\n"
                f"AREA: {area_name} already on changing room!\n"
                f"running func info: old_room_id: {old_room_id}, call_by: {old_call_by}\n"
                f"info about me: {old_room_id}, call by: {call_by}. now waiting [{sign}]..."
            )

            while True:
                await asyncio.sleep(0.2)
                change_info = self.__lock_when_changing_room.get(area_id)
                if not change_info:
                    break

            logging.error(f"[{sign}]\n{'-' * 80}")

        self.__lock_when_changing_room[area_id] = [old_room_id, call_by]
        # 加锁完毕

        flag, new_room_id = await BiliApi.search_live_room(area=area_id, old_room_id=old_room_id)
        if not flag:
            logging.error(f"Force change room error, search_live_room_error: {new_room_id}")
            return

        if new_room_id:
            logging.info(
                f"New live room from area {area_name} found, "
                f"room_id old to new: {old_room_id} -> {new_room_id}"
            )
            await self.update_clients_of_single_area(room_id=new_room_id, area_id=area_id)

        # 解锁 ！！！
        del self.__lock_when_changing_room[area_id]

    async def update_clients_of_single_area(self, room_id, area_id):
        area_name = self.AREA_MAP[area_id]
        client = self.__rws_clients.get(area_id)
        if client:
            await client.kill()

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                await self.on_message(area_id, room_id, msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_shut_down():
            logging.warning(f"Client shutdown! room_id: {room_id}, area: {area_name}")

        async def on_error(e, msg):
            logging.error(f"Listener CATCH ERROR: {msg}. e: {e}")

        new_client = RCWebSocketClient(
            url=WsApi.BILI_WS_URI,
            on_message=on_message,
            on_error=on_error,
            on_connect=on_connect,
            on_shut_down=on_shut_down,
            heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
            heart_beat_interval=10
        )
        new_client.room_id = room_id
        self.__rws_clients[area_id] = new_client
        await new_client.start()

        logging.info(f"WS client created, room_id: {room_id}, area: {area_name}")

    async def check_status(self):
        for area_id in [1, 2, 3, 4, 5, 6]:
            area_name = self.AREA_MAP[area_id]
            client = self.__rws_clients.get(area_id)
            room_id = getattr(client, "room_id", None)

            flag, active = await BiliApi.check_live_status(room_id, area_id)
            if not flag:
                logging.error(f"Cannot get live status of room: {room_id} from area: {area_name}, e: {active}")
                continue

            if not active:
                logging.info(f"Room [{room_id}] from area [{area_name}] not active, change it.")
                await self.force_change_room(old_room_id=room_id, area_id=area_id, call_by="check_status")
                continue

            if client and client.status != "OPEN":
                logging.error(
                    f"WS status Error! room_id: {room_id}, area: {area_name}, "
                    f"status: {client.status}, set_shutdown: {client.set_shutdown}"
                )

    async def run_forever(self):
        while True:
            await self.check_status()
            await asyncio.sleep(120)


async def main():
    logging.info("Start lt TV source proc...")

    tv_scanner = TvScanner()
    await tv_scanner.run_forever()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
