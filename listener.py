import json
import socket
import asyncio
import datetime
import traceback

from utils.ws import ReConnectingWsClient, State
from utils.biliapi import BiliApi, WsApi
from utils.dao import GiftRedisCache

from config.log4 import listener_logger as logging
from config.log4 import status_logger
from config import PRIZE_SOURCE_PUSH_ADDR, REDIS_CONFIG


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

    def __init__(self, message_putter):
        self.__rws_clients = {}
        self.message_putter = message_putter

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
                await self.message_putter("T", real_room_id)

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


class PrizeProcessor(object):
    def __init__(self):
        self.__room_id_pool = set()
        self.__info_setter = GiftRedisCache(
            REDIS_CONFIG["host"],
            REDIS_CONFIG["port"],
            db=REDIS_CONFIG["db"],
            password=REDIS_CONFIG["auth_pass"]
        )

    @staticmethod
    def send_prize_info(msg):
        logging.info(f"Listener: Send gift info key to server: {msg}")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(msg.encode("utf-8"), PRIZE_SOURCE_PUSH_ADDR)
        s.close()

    async def proc_single_gift_of_guard(self, room_id, gift_info):
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

    async def get_uid_by_name(self, user_name, cookie, retry_times=3):
        for retry_time in range(retry_times):
            r, uid = await BiliApi.get_user_id_by_search_way(user_name)
            if r:
                return True, uid

            logging.warning(f"Cannot get uid by search, try other way. "
                            f"retry times: {retry_time}, search result: {uid}")

            flag, r = await BiliApi.add_admin(user_name, cookie)
            if not flag:
                logging.error(f"Ignored error when add_admin: {r}")

            flag, admin_list = await BiliApi.get_admin_list(cookie)
            if not flag:
                logging.error(f"Cannot get admin list: {admin_list}, retry time: {retry_time}")
                continue

            uid = None
            for admin in admin_list:
                if admin.get("uname") == user_name:
                    uid = admin.get("uid")
                    break
            if uid:
                flag, r = await BiliApi.remove_admin(uid, cookie)
                if not flag:
                    logging.error(f"Ignored error in remove_admin: {r}")
                return True, uid
        return False, None

    async def proc_tv_gifts_by_single_user(self, user_name, gift_list):
        try:
            with open("data/cookie.json", "r") as f:
                cookies = json.load(f)
            cookie = cookies.get("RAW_COOKIE_LIST", [""])[0]
        except Exception as e:
            logging.error(
                f"Error when read cookies: {str(e)}. Do not search uid for user {user_name}. "
                f"gift_list length: {len(gift_list)}", exc_info=True)
            uid = None
        else:
            flag, uid = await self.get_uid_by_name(user_name, cookie, retry_times=3)
            if flag:
                logging.info(f"Get user info: {user_name}: {uid}. gift_list length: {len(gift_list)}.")
            else:
                logging.error(f"Cannot get uid for user: {user_name}")
                uid = None

        for info in gift_list:
            info["uid"] = uid
            room_id = info["room_id"]
            gift_id = info["gift_id"]
            key = f"_T{room_id}${gift_id}"
            result = await self.__info_setter.non_repeated_save(key, info)
            if result:
                self.send_prize_info(key)

    async def proc_single_room(self, room_id, g_type):
        if g_type == "G":
            flag, gift_info_list = await BiliApi.get_guard_raffle_id(room_id)
            if not flag:
                logging.error(f"Guard proc_single_room, room_id: {room_id}, e: {gift_info_list}")
                return

            for gift_info in gift_info_list:
                await self.proc_single_gift_of_guard(room_id, gift_info=gift_info)

        elif g_type == "T":
            flag, gift_info_list = await BiliApi.get_tv_raffle_id(room_id)
            if not flag:
                logging.error(f"TV proc_single_room, room_id: {room_id}, e: {gift_info_list}")
                return

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
                await self.proc_single_room(room_id, g_type)
            await asyncio.sleep(0.5)


class GuardScanner(object):
    def __init__(self, message_putter):
        self.message_putter = message_putter

    async def search(self):
        flag, r = await BiliApi.get_guard_room_list()
        if not flag:
            logging.error(f"Cannot find guard room. r: {r}")
            return

        for room_id in r:
            await self.message_putter("G", room_id)

    async def run_forever(self):
        await asyncio.sleep(10)
        while True:
            await self.search()
            await asyncio.sleep(60*5)


async def main():
    logging.info("Start listener proc...")

    def on_task_done(s):
        logging.error(f"Task unexpected done! {s}")

    p = PrizeProcessor()

    guard_scanner = GuardScanner(message_putter=p.add_gift)
    guard_task = asyncio.create_task(guard_scanner.run_forever())
    guard_task.add_done_callback(on_task_done)

    tv_scanner = TvScanner(message_putter=p.add_gift)
    tv_task = asyncio.create_task(tv_scanner.run_forever())
    tv_task.add_done_callback(on_task_done)

    await p.run_forever()
    await guard_task
    await tv_task


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
