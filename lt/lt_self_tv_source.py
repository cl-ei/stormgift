import asyncio
import requests
from utils.ws import ReConnectingWsClient, State
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
        data = {
            "action": "prize_notice",
            "key_type": "T",
            "room_id": room_id
        }
        try:
            r = requests.get(url=self.post_prize_url, data=data, timeout=0.5)
            print(f"r: {r}, {r.status_code}, {r.content}")
            assert r.status_code == 200
            assert "OK" in r.content.decode("utf-8")
        except Exception as e:
            error_message = F"Prize room post failed. room_id: {room_id}, e: {e}"
            logging.error(error_message, exc_info=True)
            return

        logging.info(f"TV Prize key post success: {room_id}")

    async def on_message(self, area, room_id, message):
        cmd = message.get("cmd")
        if cmd == "PREPARING":
            logging.warning(f"Room {room_id} from area {self.AREA_MAP[area]} closed! now search new.")
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
        logging.info(f"Create_client, room_id: {room_id}, area: {self.AREA_MAP[area]}")

        client = self.__rws_clients.get(area)
        if client:
            if client.status not in ("stopping", "stopped"):
                await client.kill()
            else:
                logging.error(
                    f"CLDBG_ client status is not stopping or stopped when try to close it."
                    f"area: {self.AREA_MAP[area]}, update_room_id: {room_id}, "
                    f"client_room_id: {getattr(client, 'room_id', '--')}, client_status: {client.status}, "
                    f"inner status: {await client.get_inner_status()}"
                )

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                await self.on_message(area, room_id, msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_shut_down():
            logging.warning(f"Client shutdown! room_id: {room_id}, area: {self.AREA_MAP[area]}")

        async def on_error(e, msg):
            logging.error(f"Listener CATCH ERROR: {msg}. e: {e}")

        new_client = ReConnectingWsClient(
            uri=WsApi.BILI_WS_URI,
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

    async def check_status(self):
        for area_id in [1, 2, 3, 4, 5, 6]:
            client = self.__rws_clients.get(area_id)
            if client is None:
                logging.error(f"None client for area: {self.AREA_MAP[area_id]}!")
            else:
                status = await client.get_inner_status()
                if status != State.OPEN:
                    room_id = getattr(client, "room_id", None)
                    outer_status = client.status
                    msg = (
                        f"Client state Error! room_id: {room_id}, area: {self.AREA_MAP[area_id]}, "
                        f"state: {status}, outer_statues: {outer_status}."
                    )
                    logging.error(msg)
                    status_logger.info(msg)

            room_id = getattr(client, "room_id", None)
            flag, status = await BiliApi.check_live_status(room_id, area_id)
            if not flag:
                logging.error(f"Request error when check live room status. "
                              f"room_id: {self.AREA_MAP[area_id]} -> {room_id}, e: {status}")
                continue

            if not status:
                logging.warning(f"Room [{room_id}] from area [{self.AREA_MAP[area_id]}] not active, change it.")
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
