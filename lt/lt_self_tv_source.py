import asyncio
import requests
from utils.ws import RCWebSocketClient
from utils.biliapi import BiliApi, WsApi
from config.log4 import lt_source_logger as logging
from config.log4 import status_logger
from config import LT_RAFFLE_ID_GETTER_HOST, LT_RAFFLE_ID_GETTER_PORT


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
        self.post_prize_url = f"http://{LT_RAFFLE_ID_GETTER_HOST}:{LT_RAFFLE_ID_GETTER_PORT}"
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

    async def on_message(self, area, room_id, message):
        cmd = message.get("cmd")
        if cmd == "PREPARING":
            logging.warning(f"Room {room_id} from area {self.AREA_MAP[area]} closed! now force_change_room.")
            await self.force_change_room(old_room_id=room_id, area=area)

        elif cmd == "NOTICE_MSG":
            msg_self = message.get("msg_self", "")
            matched_notice_area = False
            if area == 1 and msg_self.startswith("全区"):
                matched_notice_area = True
            elif msg_self.startswith(self.AREA_MAP[area]):
                matched_notice_area = True

            if matched_notice_area:
                real_room_id = message.get("real_roomid", 0)
                logging.info(
                    f"PRIZE: [{msg_self[:2]}] room_id: {real_room_id}, msg: {msg_self}. "
                    f"source: {area}-{room_id}"
                )
                self.post_prize_info(real_room_id)

    async def force_change_room(self, old_room_id, area):
        flag, new_room_id = await BiliApi.search_live_room(area=area, old_room_id=old_room_id)
        if not flag:
            logging.error(f"Force change room error, search_live_room_error: {new_room_id}")
            return

        if new_room_id:
            await self.update_clients_of_single_area(room_id=new_room_id, area=area)

    async def update_clients_of_single_area(self, room_id, area):
        client = self.__rws_clients.get(area)
        if client:
            await client.kill()

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                await self.on_message(area, room_id, msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_shut_down():
            logging.warning(f"Client shutdown! room_id: {room_id}, area: {self.AREA_MAP[area]}")

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
        self.__rws_clients[area] = new_client
        await new_client.start()

        logging.info(f"WS client created, room_id: {room_id}, area: {self.AREA_MAP[area]}")

    async def check_status(self):
        for area_id in [1, 2, 3, 4, 5, 6]:
            area = self.AREA_MAP[area_id]
            client = self.__rws_clients.get(area_id)
            room_id = getattr(client, "room_id", None)

            flag, active = await BiliApi.check_live_status(room_id, area_id)
            if not flag:
                logging.error(f"Cannot get live status of room: {room_id} from area: {area} ")
                return

            if active:
                if client and client.status != "OPEN":
                    msg = f"WS state Error! room_id: {room_id}, area: {area}, status: {client.status}"
                    logging.error(msg)
                    status_logger.info(msg)
            else:
                logging.info(f"Room [{room_id}] from area [{area}] not active, change it.")
                await self.force_change_room(old_room_id=room_id, area=area_id)

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
