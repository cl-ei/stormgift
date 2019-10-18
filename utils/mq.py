import time
import aiohttp
import asyncio
from aiohttp import web
from random import random
from asyncio.queues import Queue
from utils.dao import redis_cache
from config.log4 import lt_source_logger as logging


class CLMessageQServer:
    server_port = 40000
    path = "/lt/local/mq"

    def __init__(self):
        self.queue_list = []

    @staticmethod
    async def replace_unread_message():
        async def proc_single_queue(name):
            queue_origin_name = name.replace("_R_", "_", 1)
            message_id_list = await redis_cache.list_get_all(name)

            for message_id in message_id_list:
                value = await redis_cache.get(message_id)
                if not isinstance(value, dict):
                    continue

                read_time = value.get("read_time", time.time())
                interval = time.time() - read_time
                if interval < 20:
                    continue

                elif interval < 55:
                    logging.info(f"Return message: {message_id}: {value}")
                    del value["read_time"]
                    await redis_cache.set(message_id, value, timeout=3600)
                    await redis_cache.list_del(name, message_id)
                    await redis_cache.list_push(queue_origin_name, message_id)

                else:
                    await redis_cache.delete(message_id)
                    await redis_cache.list_del(name, message_id)

        reading_queues = await redis_cache.keys("CLMQ_R_*")
        for q_name in reading_queues:
            await proc_single_queue(q_name)

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
        app.add_routes([web.route('*', self.path, handler)])
        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, '127.0.0.1', self.server_port)
        await site.start()

        while True:
            await self.replace_unread_message()
            await asyncio.sleep(10)


class CLMessageQ:
    def __init__(self, queue_name):
        self.queue_name = f"CLMQ_{queue_name}"
        self.reading_queue_name = f"CLMQ_R_{queue_name}"

    async def put(self, message):
        value = {
            "body": message,
            "created_time": time.time(),
        }
        while True:
            message_id = f"M_{int(time.time())}_{int(str(random())[2:]):x}"
            set_success = await redis_cache.set_if_not_exists(key=message_id, value=value)
            if set_success:
                break

        await redis_cache.list_push(self.queue_name, message_id)

        req_url = F"http://127.0.0.1:{CLMessageQServer.server_port}{CLMessageQServer.path}"
        client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1))
        try:
            async with client_session as session:
                async with session.put(req_url, headers={"message_id": message_id}) as resp:
                    return message_id
        except Exception as e:
            logging.error(f"CLMessageQ Error: {e}")

        return message_id

    async def get(self):
        while True:
            message_id = await redis_cache.list_rpop_to_another_lpush(self.queue_name, self.reading_queue_name)
            if message_id:
                value = await redis_cache.get(message_id)
                value["read_time"] = time.time()
                await redis_cache.set(key=message_id, value=value, timeout=3600)

                q_name = self.reading_queue_name

                async def has_read():
                    await redis_cache.list_del(q_name, message_id)

                return value["body"], has_read

            req_url = F"http://127.0.0.1:{CLMessageQServer.server_port}{CLMessageQServer.path}"
            timeout = aiohttp.ClientTimeout(total=60)
            client_session = aiohttp.ClientSession(timeout=timeout)
            try:
                async with client_session as session:
                    async with session.get(req_url) as resp:
                        status_code = resp.status
                        if status_code != 200:
                            continue
            except Exception as e:
                logging.error(f"Warning happened when waiting for triggering: {e}")
                await asyncio.sleep(0.5)
                continue


mq_source_to_raffle = CLMessageQ("STOR")
mq_raffle_to_acceptor = CLMessageQ("RTOA")
mq_raffle_broadcast = CLMessageQ("RF_BROADCAST")

if __name__ == "__main__":
    async def server():
        s = CLMessageQServer()
        await s.run()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(server())
