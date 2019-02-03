import datetime
import socket
import json
import asyncio

from config import PRIZE_SOURCE_PUSH_ADDR, REDIS_CONFIG
from utils.ws import ReConnectingWsClient
from utils.biliapi import BiliApi, WsApi
from utils.dao import GiftRedisCache


class ClientManager(object):
    AREA_MAP = {
        0: "全区",
        1: "娱乐",
        2: "网游",
        3: "手游",
        4: "绘画",
        5: "电台",
        6: "单机",
    }

    def __init__(self, message_putter):
        self.__rws_clients = {}
        self.message_putter = message_putter

    async def on_message(self, area, room_id, message):
        cmd = message.get("cmd")
        if cmd == "PREPARING":
            print(f"Room {room_id} from area {self.AREA_MAP[area]} closed! now search new.")
            await self.force_change_room(old_room_id=room_id, area=area)
        elif cmd == "NOTICE_MSG":
            msg_self = message.get("msg_self", "")
            if msg_self.startswith(self.AREA_MAP[area]):
                real_room_id = message.get("real_roomid", 0)
                await self.message_putter("T", real_room_id)

    async def force_change_room(self, old_room_id, area):
        if area == 0:
            new_room_id = 4424139
        else:
            new_room_id = await BiliApi.search_live_room(area=area, old_room_id=old_room_id)
        if new_room_id:
            await self.update_clients_of_single_area(room_id=new_room_id, area=area)

    async def update_clients_of_single_area(self, room_id, area):
        print(f"Create_client, room_id: {room_id}, area: {self.AREA_MAP[area]}")

        client = self.__rws_clients.get(area)
        if client and client.status not in ("stopping", "stopped"):
            await client.kill()

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                await self.on_message(area, room_id, msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_shut_down():
            print("shut done! %s, area: %s" % (room_id, self.AREA_MAP[area]))

        new_client = ReConnectingWsClient(
            uri=WsApi.BILI_WS_URI,  # "ws://localhost:22222",
            on_message=on_message,
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
            room_id = getattr(client, "room_id", None)
            status = await BiliApi.check_live_status(room_id, area_id)
            if not status:
                await self.force_change_room(old_room_id=room_id, area=area_id)

    async def run(self):
        await self.force_change_room(old_room_id=None, area=0)
        while True:
            await self.check_status()
            await asyncio.sleep(60*2)


class PrizeProcessor(object):
    def __init__(self):
        self.__room_id_pool = set()
        self.__info_setter = GiftRedisCache(
            REDIS_CONFIG["host"],
            REDIS_CONFIG["port"],
            db=1,
            password=REDIS_CONFIG["password"]
        )

    @staticmethod
    def send_prize_info(msg):
        print("send key: %s" % msg)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(json.dumps(msg).encode("utf-8"), PRIZE_SOURCE_PUSH_ADDR)
        s.close()

    async def proc_single_gift_of_guard(self, room_id, gift_info):
        print(f"proc_single_gift_of_guard: %s" % gift_info)
        info = {
            "uid": gift_info.get("sender").get("uid"),
            "name": gift_info.get("sender").get("uname"),
            "face": gift_info.get("sender").get("face"),
            "room_id": room_id,
            "gift_id": gift_info.get("id", 0),
            "gift_name": "guard",
            "gift_type": "G%s" % gift_info.get("privilege_type"),
            "sender_type": None,
            "created_time": str(datetime.datetime.now())[:19],
            "status": gift_info.get("status")
        }
        key = f"NG{room_id}${gift_info.get('id', 0)}"
        result = await self.__info_setter.non_repeated_save(key, info)
        if result:
            self.send_prize_info(key)

    async def proc_tv_gifts_by_single_user(self, user_name, gift_list):
        try:
            with open("data/cookie.json", "r") as f:
                cookies = json.load(f)
            cookie = cookies.get("RAW_COOKIE_LIST", [""])[0]
        except Exception:
            # TODO: add log
            uid = None
        else:
            result, uid = await BiliApi.get_user_id_by_name(user_name, cookie, retry_times=3)
            if not result:
                # TODO: add log
                uid = None
            else:
                print(f"User {user_name} found: {uid}")

        for info in gift_list:
            info["uid"] = uid
            room_id = info["room_id"]
            gift_id = info["gift_id"]
            key = f"NG{room_id}${gift_id}"
            result = await self.__info_setter.non_repeated_save(key, info)
            if result:
                self.send_prize_info(key)

    async def proc_single_room(self, room_id, g_type):
        if g_type == "G":
            gift_info_list = await BiliApi.get_guard_raffle_id(room_id, return_detail=True)
            for gift_info in gift_info_list:
                await self.proc_single_gift_of_guard(room_id, gift_info=gift_info)
        elif g_type == "T":
            gift_info_list = await BiliApi.get_tv_raffle_id(room_id, return_detail=True)
            result = {}
            for info in gift_info_list:
                user_name = info.get("from_user").get("uname")
                i = {
                    "name": user_name,
                    "face": info.get("from_user").get("face"),
                    "room_id": room_id,
                    "gift_id": info.get("raffleId", 0),
                    "gift_name": info.get("title"),
                    "gift_type": info.get("type"),
                    "sender_type": info.get("sender_type"),
                    "created_time": str(datetime.datetime.now())[:19],
                    "status": info.get("status")
                }
                result.setdefault(user_name, []).append(i)
            for user_name, gift_list in result.items():
                await self.proc_tv_gifts_by_single_user(user_name, gift_list)

    async def add_gift(self, g_type, room_id):
        g_type = g_type.upper()
        if g_type in ("T", "G"):
            key = f"{g_type}${room_id}"
            self.__room_id_pool.add(key)

    async def run_forever(self):
        while True:
            while self.__room_id_pool:
                key = self.__room_id_pool.pop()
                g_type, room_id = key.split("$", 1)
                room_id = int(room_id)
                try:
                    await self.proc_single_room(room_id, g_type)
                except Exception as e:
                    print("Exception: %s" % e)

                    import traceback
                    print(traceback.format_exc())

            await asyncio.sleep(0.5)


class GuardScanner(object):
    def __init__(self, message_putter):
        self.message_putter = message_putter

    async def search(self):
        for room_id in await BiliApi.get_guard_room_list():
            await self.message_putter("G", room_id)

    async def run_forever(self):
        await asyncio.sleep(10)
        while True:
            await self.search()
            await asyncio.sleep(60*5)


async def main():
    p = PrizeProcessor()

    guard_scanner = GuardScanner(p.add_gift)
    m = ClientManager(p.add_gift)

    def on_tesk_done(s):
        print(f"Task unexpected done! {s}")

    tv_proc_task = asyncio.create_task(p.run_forever())
    tv_proc_task.add_done_callback(on_tesk_done)

    guard_proc_task = asyncio.create_task(guard_scanner.run_forever())
    guard_proc_task.add_done_callback(on_tesk_done)

    await m.run()
    print("Task stopped!")
    await tv_proc_task
    await guard_proc_task


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
