import asyncio
import websockets
from websockets.protocol import State


class ReConnectingWsClient(object):
    def __init__(self, uri,
                 on_message=None,
                 on_connect=None,
                 on_shut_down=None,
                 heart_beat_pkg="heart beat",
                 heart_beat_interval=10,
                 ):
        self.retry_times = 0
        self.server_uri = uri

        self.status = "init"
        self.__task = None
        self.__client = None

        self.on_message = on_message
        self.on_connect = on_connect
        self.on_shut_down = on_shut_down
        self.heart_beat_package = heart_beat_pkg
        self.heart_beat_interval = heart_beat_interval

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
                # print("Error happened: %s" % e)
                pass

        task = asyncio.create_task(catch_connect_error())
        task.add_done_callback(self._reconnect_cb)
        self.__task = task

    async def kill(self):
        self.status = "stopping"
        if self.__client:
            await self.__client.close()
        if not self.__task.cancelled():
            self.__task.remove_done_callback(self._reconnect_cb)

            def call_back(t):
                self.status = "stopped"
                if self.on_shut_down:
                    asyncio.gather(self.on_shut_down())
            self.__task.add_done_callback(call_back)
            self.__task.cancel()

    async def get_inner_status(self):
        return getattr(self.__client, "state", None)

    async def connect(self):
        async with websockets.connect(self.server_uri) as ws:
            self.status = "connected"
            self.retry_times = 0
            self.__client = ws

            if self.on_connect:
                await self.on_connect(ws)

            async def send_heart_beat():
                while not ws.closed:
                    await asyncio.sleep(self.heart_beat_interval)
                    try:
                        await ws.send(self.heart_beat_package)
                    except Exception as e:
                        # print("Error in send heart beat e: %s" % e)
                        return
            heart_beat_task = asyncio.create_task(send_heart_beat())

            while not ws.closed:
                try:
                    data = await ws.recv()
                    if self.on_message:
                        await self.on_message(data)
                except Exception as e:
                    # print("Error in receiving msg: %s" % e)
                    break
            heart_beat_task.cancel()

        if self.status not in ("stopping", "stopped"):
            self.status = "reconnecting"
