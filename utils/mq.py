import time
import aiohttp
import asyncio
import traceback
from aiohttp import web
from random import random
from asyncio.queues import Queue
from utils.dao import redis_cache
from config.log4 import lt_source_logger as logging


class SourceToRaffleMQ(object):
    req_url = "http://127.0.0.1:40000/lt/local/proc_raffle"

    @classmethod
    async def _request(cls, url, message, timeout=10):
        client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))
        try:
            async with client_session as session:
                async with session.post(url, json=message) as resp:
                    status_code = resp.status
                    if status_code in (200, 204, 206):
                        return True, ""

                    content = await resp.text()
                    return False, content

        except asyncio.TimeoutError:
            return False, f"Request timeout({timeout} second(s).)."

        except Exception as e:
            return False, f"Error happend: {e}\n {traceback.format_exc()}"

    @classmethod
    async def put(cls, danmaku, created_time, msg_from_room_id):
        s = time.time()
        message = {"danmaku": danmaku, "created_time": created_time, "msg_from_room_id": msg_from_room_id}
        r = await cls._request(url=cls.req_url, message=message)

        spend = time.time() - s
        logging.info(f">>> SourceToRaffleMQ PUT time: {spend:.3f}")

        return r


class RaffleToAcceptorMQ(object):
    @classmethod
    async def put(cls, key):
        s = time.time()

        req_url = f"http://127.0.0.1:40001/lt/local/acceptor/{key}"
        timeout = aiohttp.ClientTimeout(total=10)
        client_session = aiohttp.ClientSession(timeout=timeout)
        try:
            async with client_session as session:
                async with session.post(req_url) as resp:
                    status_code = resp.status
                    if status_code in (200, 204, 206):
                        result = True, ""
                    else:
                        result = False, ""
        except Exception as e:
            result = False, f"Error happened in RaffleToAcceptorMQ: {e}"

        spend = time.time() - s
        logging.info(f">>> RaffleToAcceptorMQ PUT time: {spend:.3f}")

        return result


class CLMessageQServer:
    server_port = 44488

    def __init__(self):
        self.queue_list = []

    async def run(self):
        queue_list = self.queue_list

        async def handler(request):
            if request.method == "PUT":
                message_id = request.headers["message_id"]
                for q in queue_list:
                    q.put_nowait(message_id)
                return web.Response(text=f"OK! Client length: {len(queue_list)}")

            receiver_queue = Queue()
            queue_list.append(receiver_queue)

            async def shutdown():
                await asyncio.sleep(50)
                receiver_queue.put_nowait(Exception("Done"))

            timer = asyncio.create_task(shutdown())
            message_id = await receiver_queue.get()
            self.queue_list.remove(receiver_queue)

            if isinstance(message_id, Exception):
                return web.HTTPNotFound()

            timer.cancel()
            return web.Response(text=message_id)

        app = web.Application()
        app.add_routes([web.route('*', '/lt/local/mq', handler)])
        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, '127.0.0.1', self.server_port)
        await site.start()

        while True:
            await asyncio.sleep(20)


class CLMessageQ:
    def __init__(self, queue_name):
        self.queue_name = f"CLMQ_{queue_name}"
        self.reading_queue_name = f"CLMQ_{queue_name}_reading"

    async def put(self, message):
        while True:
            message_id = f"{int(time.time())}_{int(str(random())[2:]):x}"

            detail_key = f"{self.queue_name}_{message_id}"
            existed = await redis_cache.set_if_not_exists(key=detail_key, value=message)
            if not existed:
                break

        await redis_cache.list_push(self.queue_name, message_id)
        return message_id

    async def get(self):
        message_id = await redis_cache.list_rpop_to_another_lpush(self.queue_name, self.reading_queue_name)
        if message_id:
            detail_key = f"{self.queue_name}_{message_id}"
            message = await redis_cache.get(detail_key)
            if message:
                reading_time_key = f"{self.queue_name}_{message_id}_rt"
                await redis_cache.set(reading_time_key, time.time())
            else:
                await redis_cache.list_del(self.reading_queue_name, message_id)
            return message
        return None

    async def has_read(self, message_id):
        return await redis_cache.list_del(self.reading_queue_name, message_id)

