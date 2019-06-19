import sys
import time
import asyncio
import datetime
import requests
import traceback
from aiohttp import web
from queue import Empty
from multiprocessing import Process, Queue
from utils.biliapi import BiliApi
from config.log4 import lt_raffle_id_getter_logger as logging
from config import LT_RAFFLE_ID_GETTER_HOST, LT_RAFFLE_ID_GETTER_PORT, LT_ACCEPTOR_HOST, LT_ACCEPTOR_PORT
from utils.dao import redis_cache

# ACCEPT URL: http://127.0.0.1:30000?action=prize_notice&key_type=T&room_id=123


class Executor(object):
    def __init__(self):
        self.cookie_file = "data/valid_cookies.txt"
        self.post_prize_url = f"http://{LT_ACCEPTOR_HOST}:{LT_ACCEPTOR_PORT}"

    def load_a_cookie(self):
        try:
            with open(self.cookie_file, "r") as f:
                cookies = [c.strip() for c in f.readlines()]
            return cookies[0]
        except:
            return ""

    def send_prize_info(self, *args):
        key = "$".join([str(_) for _ in args])

        key_type, room_id, gift_id, *_ = args
        params = {
            "action": "prize_key",
            "key_type": key_type,
            "room_id": room_id,
            "gift_id": gift_id
        }
        try:
            r = requests.get(url=self.post_prize_url, params=params, timeout=2)
        except Exception as e:
            error_message = f"Http request error: {e}"
            logging.error(error_message)
            return

        if r.status_code != 200 or "OK" not in r.content.decode("utf-8"):
            logging.error(
                F"Prize key post failed. code: {r.status_code}, "
                F"response: {r.content}. key: {key_type}${room_id}${gift_id}"
            )
            return

        logging.info(f"Prize key post success: {key}")

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
        gift_id = gift_info.get('id', 0)
        key = f"NG{room_id}${gift_id}"
        await redis_cache.non_repeated_save(key, info)
        self.send_prize_info("G", room_id, gift_id)

    async def force_get_uid_by_name(self, user_name):
        cookie = self.load_a_cookie()
        if not cookie:
            logging.error("Cannot load cookie!")
            return None

        for retry_time in range(3):
            r, uid = await BiliApi.get_user_id_by_search_way(user_name)
            if r and isinstance(uid, (int, float)) and uid > 0:
                return uid

            # Try other way
            await BiliApi.add_admin(user_name, cookie)

            flag, admin_list = await BiliApi.get_admin_list(cookie)
            if not flag:
                continue

            uid = None
            for admin in admin_list:
                if admin.get("uname") == user_name:
                    uid = admin.get("uid")
                    break
            if isinstance(uid, (int, float)) and uid > 0:
                await BiliApi.remove_admin(uid, cookie)
                return uid
        return None

    async def proc_tv_gifts_by_single_user(self, user_name, gift_list):
        uid = await self.force_get_uid_by_name(user_name)

        for info in gift_list:
            info["uid"] = uid
            room_id = info["room_id"]
            gift_id = info["gift_id"]
            key = f"_T{room_id}${gift_id}"
            await redis_cache.non_repeated_save(key, info)
            self.send_prize_info("T", room_id, gift_id)

    async def __call__(self, args):
        key_type, room_id, *_ = args
        room_id = await BiliApi.force_get_real_room_id(room_id)

        if key_type == "G":
            flag, gift_info_list = await BiliApi.get_guard_raffle_id(room_id)
            if not flag:
                logging.error(f"Guard proc_single_room, room_id: {room_id}, e: {gift_info_list}")
                return

            for gift_info in gift_info_list:
                await self.proc_single_gift_of_guard(room_id, gift_info=gift_info)

        elif key_type == "T":
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


class AsyncHTTPServer(object):
    def __init__(self, q, host="127.0.0.1", port=8080):
        self.__q = q
        self.host = host
        self.port = port

    async def handler(self, request):
        action = request.query.get("action")
        if action != "prize_notice":
            return web.Response(text=f"Error Action.", content_type="text/html")

        try:
            key_type = request.query.get("key_type")
            room_id = int(request.query.get("room_id"))
            assert room_id > 0 and key_type in ("T", "G")
        except Exception as e:
            error_message = f"Param Error: {e}."
            return web.Response(text=error_message, content_type="text/html")

        self.__q.put_nowait((key_type, room_id))
        return web.Response(text=f"OK", content_type="text/html")

    def __call__(self):
        app = web.Application()
        app.add_routes([web.get('/', self.handler)])

        logging.info(f"Start server on: {self.host}:{self.port}")
        try:
            web.run_app(app, host=self.host, port=self.port)
        except Exception as e:
            logging.exception(f"Exception: {e}\n", exc_info=True)


class AsyncWorker(object):
    def __init__(self, http_server_proc, q, target):
        self.__http_server = http_server_proc
        self.__q = q
        self.__exc = target

    async def handler(self):
        while True:
            fe_status = self.__http_server.is_alive()
            if not fe_status:
                logging.error(f"Http server is not alive! exit now.")
                sys.exit(1)

            try:
                msg = self.__q.get(timeout=30)
            except Empty:
                continue

            start_time = time.time()
            logging.info(f"Task starting... msg: {msg}")
            try:
                r = await self.__exc(msg)
            except Exception as e:
                r = f"Error: {e}, {traceback.format_exc()}"
            cost_time = time.time() - start_time
            logging.info(f"Task finished. cost time: {cost_time}, result: {r}")

    def __call__(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.handler())


def main():
    logging.info("Starting listener process...")

    q = Queue()

    server = AsyncHTTPServer(q=q, host=LT_RAFFLE_ID_GETTER_HOST, port=LT_RAFFLE_ID_GETTER_PORT)
    p = Process(target=server, daemon=True)
    p.start()

    worker = AsyncWorker(p, q=q, target=Executor())
    worker()

    logging.warning("CQ listener process shutdown!")


if __name__ == "__main__":
    main()
