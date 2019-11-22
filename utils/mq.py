import time
import random
import pickle
import aiohttp
import asyncio
import traceback
from aiohttp import web
from asyncio.queues import Queue
from utils.dao import redis_cache, RedisLock
from config.log4 import lt_source_logger as logging


class CLMessageQServer:
    server_port = 40000
    path = "/lt/local/mq"

    def __init__(self):
        self.queue_list = []

    async def handle_put(self, request):
        if request.method == "PUT":
            message = request.headers["message"]
            for q in self.queue_list:
                q.put_nowait(message)
            return web.Response(text=f"OK! Client length: {len(self.queue_list)}")

    async def handle_get(self, request):
        receiver_queue = Queue()
        self.queue_list.append(receiver_queue)

        async def shutdown():
            await asyncio.sleep(600)
            receiver_queue.put_nowait(Exception("Done"))

        timer = asyncio.create_task(shutdown())
        message = await receiver_queue.get()
        self.queue_list.remove(receiver_queue)

        if isinstance(message, Exception):
            return web.HTTPNotFound()

        timer.cancel()
        return web.Response(text="OK")

    async def run(self):
        app = web.Application()
        app.add_routes([
            web.route('put', self.path, self.handle_put),
            web.route('get', self.path, self.handle_get),
        ])
        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, '127.0.0.1', self.server_port)
        await site.start()

        while True:
            await asyncio.sleep(10)


class CLMessageQ:
    def __init__(self, queue_name):
        self.queue_name = f"CLMQ_{queue_name}"
        self.reading_queue_name = f"CLMQ_R_{queue_name}"

    async def put(self, message):
        message = pickle.dumps(message)

        async with RedisLock(key=self.queue_name) as _:
            existed = await redis_cache.list_get_all(self.queue_name)
            if message in existed:
                print("existed.")
                return
            await redis_cache.list_push(self.queue_name, message)

        # just for trigger
        req_url = F"http://127.0.0.1:{CLMessageQServer.server_port}{CLMessageQServer.path}"
        client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        try:
            async with client_session as session:
                async with session.put(req_url, headers={"message": f"{time.time()*1000:.0f}"}) as _:
                    return True
        except Exception as e:
            logging.error(f"CLMessageQ Error: {e}\n{traceback.format_exc()}")

    async def get(self):
        while True:
            async with RedisLock(key=self.queue_name) as _:
                message = await redis_cache.list_rpop(self.queue_name)
                if message:
                    try:
                        return pickle.loads(message)
                    except (pickle.UnpicklingError, TypeError) as e:
                        logging.error(f"pickle.UnpicklingError when get from CLMessageQ: {e}. m: {message}")
                        return message

            # get from server
            req_url = F"http://127.0.0.1:{CLMessageQServer.server_port}{CLMessageQServer.path}"
            timeout = aiohttp.ClientTimeout(total=610)
            client_session = aiohttp.ClientSession(timeout=timeout)
            try:
                async with client_session as session:
                    async with session.get(req_url) as resp:
                        status_code = resp.status
                        if status_code != 200:
                            continue
            except asyncio.TimeoutError:
                continue

            except aiohttp.ClientConnectionError:
                await asyncio.sleep(0.5)
                continue

            except Exception as e:
                logging.error(f"Error in mq! {e}\n{traceback.format_exc()}")
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
