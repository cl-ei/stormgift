import json
import asyncio
import websockets
from config import PRIZE_HANDLER_SERVE_ADDR


class WsClient(object):
    def __init__(self, host, port, room_id, on_message=None):
        self.room_id = room_id
        self.retry_times = 0
        self.server_uri = f"ws://{host}:{port}"

        self.status = "init"
        self.__task = None
        self.__client = None

        async def on_message_(s):
            print(s)
        self.on_message = on_message or on_message_

        def reconnect_cb(s):
            if self.status not in ("stopping", "stopped"):
                self.retry_times += 1
                if self.retry_times < 3:
                    sleep = 0.2
                elif self.retry_times < 10:
                    sleep = 0.5
                elif self.retry_times < 20:
                    sleep = 1
                else:
                    sleep = 5
                print(self.retry_times)
                asyncio.gather(self.start(sleep))
        self._reconnect_cb = reconnect_cb

    async def start(self, delay=0):
        if delay:
            await asyncio.sleep(delay)

        if self.__task and not self.__task.done():
            raise RuntimeError("Repeated task!")

        async def catch_connect_error():
            try:
                await self.connect()
            except Exception as e:
                print("Error happened: %s" % e)

        task = asyncio.create_task(catch_connect_error())
        task.add_done_callback(self._reconnect_cb)
        self.__task = task

    async def kill(self, fn=None):
        print("kill ")

        self.status = "stopping"
        if self.__client:
            await self.__client.close()
        if not self.__task.cancelled():
            self.__task.remove_done_callback(self._reconnect_cb)
            self.__task.cancel()
        self.status = "stopped"

        if fn:
            await fn()

    async def connect(self):
        async with websockets.connect(self.server_uri) as ws:
            print("Notice server connected.")
            self.status = "connected"
            self.retry_times = 0
            self.__client = ws

            async def send_heart_beat():
                while not ws.closed:
                    await asyncio.sleep(5)
                    try:
                        await ws.send("heart beat")
                    except Exception as e:
                        # print("Error in send heart beat e: %s" % e)
                        return
            heart_beat_task = asyncio.create_task(send_heart_beat())

            while not ws.closed:
                try:
                    data = await ws.recv()
                    print("Ws received: %s" % data)
                    await self.on_message(data)
                except Exception as e:
                    # print("Error in receiving msg: %s" % e)
                    break
            heart_beat_task.cancel()

        print("Notice Server disconnected.")
        self.status = "reconnecting"


# class ClientManager(object):
#     def __init__(self):
#         self.__clients = {}
#
#     async def create_client(self, room_id):
#         c = ReconnectedWsClient(*PRIZE_HANDLER_SERVE_ADDR, room_id)
#         task = asyncio.create_task(c.start())
#         # self.__clients[room_id] = (task, c)
#         return task
#
#     async def get_clients_info(self):
#         for _, task in self.__clients.items():
#             print("%s: %s" % (_, task))


async def main():
    # m = ClientManager()
    # task = await m.create_client(123)

    c = WsClient(*PRIZE_HANDLER_SERVE_ADDR, 123)
    await c.start()
    # await asyncio.sleep(5)
    #
    # async def s(): return 0
    # await c.stop()
    #
    # await asyncio.sleep(10)
    # await c.kill(s)

    while True:
        await asyncio.sleep(3)
        print("Tasks: %s" % len(asyncio.all_tasks()))
        # await m.get_clients_info()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
