import re
import sys
import time
from random import random
import asyncio
import datetime
import traceback
from aiohttp import web
from queue import Empty
from multiprocessing import Process, Queue
from utils.biliapi import BiliApi
from config.log4 import listener_logger as logging
from config import LT_LISTENER_HOST, LT_LISTENER_PORT


class Executor(object):
    def __init__(self):
        self.cookie_file = "data/valid_cookies.txt"

    async def __call__(self, args):
        key_type, room_id, *_ = args
        pass


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
    logging.warning("Starting CQ listener process shutdown!")

    q = Queue()

    server = AsyncHTTPServer(q=q, host=LT_LISTENER_HOST, port=LT_LISTENER_PORT)
    p = Process(target=server, daemon=True)
    p.start()

    worker = AsyncWorker(p, q=q, target=Executor())
    worker()

    logging.warning("CQ listener process shutdown!")


if __name__ == "__main__":
    main()
