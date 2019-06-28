import sys
import time
import asyncio
import traceback
from random import random
from utils.ws import RCWebSocketClient
from utils.biliapi import BiliApi, WsApi
from config.log4 import lt_source_logger as logging
from utils.dao import DanmakuMessageQ


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
        self._client_status_q = asyncio.queues.Queue()
        self._danmaku_message_q = asyncio.queues.Queue()

    async def find_new_live_room_and_connect_it(self, old_room_id, area_id):
        area_name = self.AREA_MAP[area_id]

        flag, new_room_id = await BiliApi.search_live_room(area=area_id, old_room_id=old_room_id)
        if not flag:
            logging.error(f"Force change room error, search_live_room_error: {new_room_id}")
            return

        logging.info(f"Area [{area_name}] find new live room {old_room_id} -> {new_room_id}")
        await self.update_clients_of_single_area(room_id=new_room_id, area_id=area_id)

    async def update_clients_of_single_area(self, room_id, area_id):
        area_name = self.AREA_MAP[area_id]
        client = self.__rws_clients.get(area_id)
        if client:
            await client.kill()
            logging.info(f"Old client killed! [{area_name}]-{client.room_id}")

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                await self._danmaku_message_q.put((area_id, room_id, msg))

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_shut_down():
            logging.warning(f"Client shutdown! room_id: [{area_name}]-{room_id}")

        async def on_error(e, msg):
            logging.error(f"Listener CATCH ERROR, room_id: [{area_name}]-{room_id},msg: {msg}. e: {e}")

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
        logging.info(f"New ws client created, [{area_name}]-{room_id}")

    async def check_status_for_single_area(self, area_id, old_room_id, called_by):
        # 检查锁并加锁
        area_name = self.AREA_MAP[area_id]
        change_info = self.__lock_when_changing_room.get(area_id)
        if change_info:
            sign = str(random())
            old_room_id, old_called_by = change_info

            logging.error(
                f"\n{'-' * 80}\n"
                f"AREA: [{area_name}] already on changing room!\n"
                f"running func info: old_room_id: {old_room_id}, old_called_by: {old_called_by}\n"
                f"info about me: {old_room_id}, call by: {called_by}. now waiting [{sign}]..."
            )

            while True:
                await asyncio.sleep(0.2)
                change_info = self.__lock_when_changing_room.get(area_id)
                if not change_info:
                    break

            logging.error(f"[{sign}] lock released!\n{'-' * 80}")

        self.__lock_when_changing_room[area_id] = [old_room_id, called_by]
        # 加锁完毕

        client = self.__rws_clients.get(area_id)
        room_id = getattr(client, "room_id", None)

        flag, active = await BiliApi.check_live_status(room_id, area_id)
        if not flag:
            logging.error(f"Cannot get live status of room: {room_id} from area: [{area_name}], e: {active}")

        elif active:
            if client and client.status != "OPEN":
                logging.error(
                    f"WS status Error! room_id: {room_id}, area: [{area_name}], "
                    f"status: {client.status}, set_shutdown: {client.set_shutdown}"
                )
        else:
            logging.info(f"Room [{room_id}] from area [{area_name}] not active, change it.")
            await self.find_new_live_room_and_connect_it(old_room_id=room_id, area_id=area_id)

        # 解锁 ！！！
        del self.__lock_when_changing_room[area_id]

    async def check_status(self):
        last_check_status_time = 0
        cyclic_check_interval = 120
        while True:
            interval = time.time() - last_check_status_time
            if interval > cyclic_check_interval:
                last_check_status_time = time.time()
                logging.info(f"Now fully check status. interval: {interval:.3f}, time: {time.time():.3f}")
                for area_id in [1, 2, 3, 4, 5, 6]:
                    old_room_id = getattr(self.__rws_clients.get(area_id), "room_id", None)
                    await self.check_status_for_single_area(
                        area_id=area_id,
                        old_room_id=old_room_id,
                        called_by="cyclic_check"
                    )

            try:
                error_status_info = self._client_status_q.get_nowait()
            except asyncio.queues.QueueEmpty:
                await asyncio.sleep(0.5)
                continue

            area_id, old_room_id = error_status_info
            await self.check_status_for_single_area(area_id=area_id, old_room_id=old_room_id, called_by="msg_trigger")

    async def parse_single_message(self, area_id, room_id, message):
        area_name = self.AREA_MAP[area_id]

        cmd = message.get("cmd")
        if cmd == "PREPARING":
            logging.warning(f"Danmaku received `PREPARING`, [{area_name}]-{room_id}.")
            await self._client_status_q.put((area_id, room_id))

        elif cmd == "NOTICE_MSG":
            msg_self = message.get("msg_self", "")
            matched_notice_area = False

            if area_id == 1 and msg_self.startswith("全区"):
                matched_notice_area = True
            elif msg_self.startswith(area_name):
                matched_notice_area = True

            if matched_notice_area:
                r = await DanmakuMessageQ.put(message, time.time(), room_id)
                logging.info(
                    f"PRIZE: [{msg_self[:2]}] room_id: {message['real_room_id']}, msg: {msg_self}. "
                    f"source: {area_id}-[{area_name}]-{room_id}, mq put result: {r}"
                )

        elif cmd == "GUARD_MSG" and message.get("buy_type") == 1 and area_id == 1:
            # {
            #   'cmd': 'GUARD_MSG',
            #   'msg': '用户 :?菜刀刀的鸭鸭:? 在主播 小菜刀夫斯基 的直播间开通了总督',
            #   'msg_new': '<%菜刀刀的鸭鸭%> 在 <%小菜刀夫斯基%> 的房间开通了总督并触发了抽奖，点击前往TA的房间去抽奖吧',
            #   'url': 'https://live.bilibili.com/7331822',
            #   'roomid': 7331822,
            #   'buy_type': 1,
            #   'broadcast_type': 0
            # }

            prize_room_id = message['roomid']  # TODO: need find real room id.
            logging.info(f"PRIZE 总督 room id: {prize_room_id}, msg: {message.get('msg_new')}")
            await DanmakuMessageQ.put(message, time.time(), room_id)

    async def parse_message(self):
        while True:
            area_id, room_id, message = await self._danmaku_message_q.get()
            await self.parse_single_message(area_id, room_id, message)

    async def run(self):
        try:
            await asyncio.gather(self.parse_message(), self.check_status())
        except Exception as e:
            logging.error(f"Process Error! e: {e} {traceback.format_exc()}\nNow exit!\n")
            sys.exit(1)


async def main():
    logging.info("Start lt TV source proc...")

    tv_scanner = TvScanner()
    await tv_scanner.run()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
