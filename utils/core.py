import re
import os
import time
import sys
import datetime
import socket
import json
import asyncio
import logging
import traceback
from utils.ws import ReConnectingWsClient, State
from utils.biliapi import BiliApi, WsApi


log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
logger = logging.getLogger("stormgift")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)
logging = logger


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
                logging.info(f"PRIZE: [{msg_self[:2]}] room_id: {real_room_id}, msg: {msg_self}")
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
        if client and client.status not in ("stopping", "stopped"):
            await client.kill()

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                await self.on_message(area, room_id, msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

        async def on_shut_down():
            logging.warning(f"Client shutdown! room_id: {room_id}, area: {self.AREA_MAP[area]}")

        new_client = ReConnectingWsClient(
            uri=WsApi.BILI_WS_URI,
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
            if client is None:
                pass
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
    def __init__(self, send_raffle_key):
        self.__room_id_pool = set()
        self.send_raffle_key = send_raffle_key

    async def send_prize_info(self, msg):
        await self.send_raffle_key(msg)

    async def proc_tv_gifts_by_single_user(self, user_name, gift_list):
        uid = None
        for info in gift_list:
            info["uid"] = uid
            room_id = info["room_id"]
            gift_id = info["gift_id"]
            key = f"_T{room_id}${gift_id}"
            await self.send_prize_info(key)

    async def proc_single_gift_of_guard(self, room_id, gift_info):
        key = f"NG{room_id}${gift_info.get('id', 0)}"
        await self.send_prize_info(key)

    async def proc_single_room(self, room_id, g_type):
        if g_type == "T":
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
        elif g_type == "G":
            flag, gift_info_list = await BiliApi.get_guard_raffle_id(room_id)
            if flag:
                for gift_info in gift_info_list:
                    await self.proc_single_gift_of_guard(room_id, gift_info=gift_info)

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


class Acceptor(object):
    def __init__(self):
        self.q = asyncio.Queue(maxsize=2000)
        self.cookie_file = "data/cookie.json"
        self.__black_list = {}

    async def add_task(self, key):
        await self.q.put(key)

    async def load_cookie(self):
        try:
            with open(self.cookie_file, "r") as f:
                c = json.load(f)
            cookie_list = c["RAW_COOKIE_LIST"]
        except Exception as e:
            logging.error(f"Bad cookie, e: {str(e)}.", exc_info=True)
            return [], []

        blacklist = []
        for index in range(0, len(cookie_list)):
            cookie = cookie_list[index]
            bt = self.__black_list.get(cookie)
            if isinstance(bt, (int, float)) and int(time.time()) - bt < 3600*12:
                blacklist.append(index)

        if len(self.__black_list) > len(cookie_list):
            new_black_list = {}
            for cookie in self.__black_list:
                if cookie in cookie_list:
                    new_black_list[cookie] = self.__black_list[cookie]
            self.__black_list = new_black_list
            logging.critical("SELF BLACK LIST GC DONE!")
        return cookie_list, blacklist

    async def add_black_list(self, cookie):
        self.__black_list[cookie] = time.time()
        user_ids = re.findall(r"DedeUserID=(\d+)", "".join(self.__black_list.keys()))
        logging.critical(f"Black list updated. current {len(user_ids)}: [{', '.join(user_ids)}].")

    async def accept_tv(self, i, room_id, gift_id, cookie):
        uid_list = re.findall(r"DedeUserID=(\d+)", cookie)
        user_id = uid_list[0] if uid_list else "Unknown-uid"

        r, msg = await BiliApi.join_tv(room_id, gift_id, cookie)
        if r:
            logging.info(f"成功参与抽奖! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
        else:
            logging.critical(f"参与抽奖失败! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
            if "访问被拒绝" in msg:
                await self.add_black_list(cookie)

    async def accept_guard(self, i, room_id, gift_id, cookie):
        uid_list = re.findall(r"DedeUserID=(\d+)", cookie)
        user_id = uid_list[0] if uid_list else "Unknown-uid"

        r, msg = await BiliApi.join_guard(room_id, gift_id, cookie)
        if r:
            logging.info(f"成功参与抽奖! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
        else:
            logging.critical(f"参与抽奖失败! {i}-{user_id}, key: {room_id}${gift_id}, msg: {msg}")
            if "访问被拒绝" in msg:
                await self.add_black_list(cookie)

    async def accept_prize(self, key):
        if not isinstance(key, str):
            key = key.decode("utf-8")

        if key.startswith("_T"):
            process_fn = self.accept_tv
        elif key.startswith("NG"):
            process_fn = self.accept_guard
        else:
            logging.error(f"invalid key: {key}. skip it.")
            return
        try:
            room_id, gift_id = map(int, key[2:].split("$"))
        except Exception as e:
            logging.error(f"Bad prize key {key}, e: {str(e)}")
            return

        cookies, black_list = await self.load_cookie()
        for i in range(len(cookies)):
            if i in black_list:
                uid_list = re.findall(r"DedeUserID=(\d+)", cookies[i])
                user_id = uid_list[0] if uid_list else "Unknown-uid"
                logging.warning(f"User {i}-{user_id} in black list, skip it.")
            else:
                await process_fn(i, room_id, gift_id, cookies[i])

    async def run_forever(self):
        while True:
            r = await self.q.get()
            await self.accept_prize(r)


class GuardScanner(object):
    def __init__(self, message_putter):
        self.message_putter = message_putter

    async def search(self):
        flag, r = await BiliApi.get_guard_room_list()
        if flag:
            for room_id in r:
                await self.message_putter("G", room_id)

    async def run_forever(self):
        await asyncio.sleep(2)
        while True:
            await self.search()
            await asyncio.sleep(60*5)


async def run_forever():
    logging.info("Start...")

    def on_task_done(s):
        err_msg = f"Task unexpected done! {s}"
        logging.error(err_msg)
        raise RuntimeError(err_msg)

    acceptor = Acceptor()
    accept_task = asyncio.create_task(acceptor.run_forever())
    accept_task.add_done_callback(on_task_done)

    prize_processor = PrizeProcessor(send_raffle_key=acceptor.add_task)

    scanner = TvScanner(message_putter=prize_processor.add_gift)
    task_scan = asyncio.create_task(scanner.run_forever())
    task_scan.add_done_callback(on_task_done)

    guard_scanner = GuardScanner(message_putter=prize_processor.add_gift)
    task_guard_scan = asyncio.create_task(guard_scanner.run_forever())
    task_guard_scan.add_done_callback(on_task_done)

    await prize_processor.run_forever()
    await task_guard_scan
    await task_scan
    await accept_task
