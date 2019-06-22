import time
import asyncio
import websockets
import traceback
from websockets.protocol import State


class ReConnectingWsClient(object):
    def __init__(self, uri,
                 on_message=None,
                 on_connect=None,
                 on_shut_down=None,
                 on_error=None,
                 heart_beat_pkg="heart beat",
                 heart_beat_interval=0,
                 ):
        self.retry_times = 0
        self.server_uri = uri

        self.status = "init"
        self.__task = None
        self.__client = None

        self.on_message = on_message
        self.on_connect = on_connect
        self.on_shut_down = on_shut_down

        if on_error:
            async def _on_error(e, msg):
                try:
                    await on_error(e, msg)
                except Exception:
                    pass
            self.on_error = _on_error
        else:
            async def _on_error(*args, **kw):
                pass
            self.on_error = _on_error

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
                await self.on_error(e, "in catch_connect_error")

        if getattr(asyncio, "create_task", None):
            task = asyncio.create_task(catch_connect_error())
        else:
            task = asyncio.ensure_future(catch_connect_error())
        task.add_done_callback(self._reconnect_cb)
        self.__task = task

    async def kill(self):
        self.status = "stopping"
        if self.__task.cancelled():
            raise RuntimeError("Task has been cancelled when cancel it!")

        self.__task.remove_done_callback(self._reconnect_cb)
        self.__task.cancel()
        if self.__client:
            await self.__client.close()
        await self.__task

        self.status = "stopped"
        if self.on_shut_down:
            await self.on_shut_down()

    async def get_inner_status(self):
        return getattr(self.__client, "state", None)

    async def connect(self):
        async with websockets.connect(self.server_uri) as ws:
            self.status = "connected"
            self.retry_times = 0
            self.__client = ws

            if self.on_connect:
                await self.on_connect(ws)

            heart_beat_task = None
            if self.heart_beat_interval > 0:
                async def send_heart_beat():
                    while not ws.closed:
                        await asyncio.sleep(self.heart_beat_interval)
                        try:
                            await ws.send(self.heart_beat_package)
                        except Exception as e:
                            await self.on_error(e, "Error in send heart beat.")

                if getattr(asyncio, "create_task", None):
                    heart_beat_task = asyncio.create_task(send_heart_beat())
                else:
                    heart_beat_task = asyncio.ensure_future(send_heart_beat())

            while not ws.closed:
                try:
                    data = await ws.recv()
                    if self.on_message:
                        await self.on_message(data)
                except Exception as e:
                    await self.on_error(e, "Error in receiving msg.")
            if heart_beat_task:
                heart_beat_task.cancel()
                await heart_beat_task

        if self.status not in ("stopping", "stopped"):
            self.status = "reconnecting"


class RCWebSocketClient(object):
    def __init__(
            self,
            url,
            on_message=None,
            on_connect=None,
            on_shut_down=None,
            on_error=None,
            heart_beat_pkg="heart beat",
            heart_beat_interval=0
    ):
        self.server_url = url

        self.__task = None
        self.__client = None
        self.__reconnecting_times = 0

        self.on_message = on_message
        self._on_connect_cb = on_connect
        self._on_error_cb = on_error
        self.on_shut_down = on_shut_down
        self.heart_beat_package = heart_beat_pkg
        self.heart_beat_interval = heart_beat_interval

        self.set_shutdown = False

    async def on_connect(self, ws):
        self.__reconnecting_times = 0
        await self._on_connect_cb(ws)

    async def on_error(self, *args, **kw):
        if self._on_error_cb and not self.set_shutdown:
            try:
                await self._on_error_cb(*args, **kw)
            except Exception as e:
                print(f"Exception on handling on_error: {e}")

    async def connect_with_handle_exception(self):
        while not self.set_shutdown:
            try:
                await self.connect()
            except Exception as e:
                await self.on_error(e, "Error in connections.")

            if self.set_shutdown:
                return

            self.__reconnecting_times += 1
            if self.__reconnecting_times <= 2:
                wait_time = 0.1
            elif self.__reconnecting_times <= 5:
                wait_time = 0.3
            elif self.__reconnecting_times <= 10:
                wait_time = 1
            else:
                wait_time = 2

            await asyncio.sleep(wait_time)

    async def start(self):
        if self.__task is not None:
            raise Exception("Task already created!")

        self.__task = asyncio.create_task(self.connect_with_handle_exception())

        if self.on_shut_down:
            self.__task.add_done_callback(lambda s: asyncio.gather(self.on_shut_down()))

    async def kill(self):
        if self.set_shutdown:
            return

        self.set_shutdown = True
        if self.__task.cancelled():
            raise Exception("Task has been cancelled when cancel it!")

        self.__task.cancel()
        if self.__client:
            if getattr(self.__client, "state", None) == 3:  # 3 -> CLOSED
                from config.log4 import lt_source_logger as logging
                logging.error("For DEBUG: client status is already closed when trying to close it.")

            await self.__client.close()
        await self.__task

    @property
    def status(self):
        status = {
            None: None,
            0: "CONNECTING",
            1: "OPEN",
            2: "CLOSING",
            3: "CLOSED",
        }[getattr(self.__client, "state", None)]

        return status

    async def connect(self):
        async with websockets.connect(self.server_url) as ws:
            ws.last_heartbeat = time.time()
            self.__client = ws

            if self.on_connect:
                await self.on_connect(ws)

            heart_beat_task = None
            if self.heart_beat_interval > 0:

                async def send_heart_beat():
                    while not ws.closed:
                        await asyncio.sleep(self.heart_beat_interval)
                        await ws.send(self.heart_beat_package)

                        interval = time.time() - ws.last_heartbeat
                        ws.last_heartbeat = time.time()
                        if interval > self.heart_beat_interval + 3:
                            print(f"WARNING!!! Heart beat interval too long! time: {interval}")

                heart_beat_task = asyncio.create_task(send_heart_beat())

            while not ws.closed:
                data = await ws.recv()
                try:
                    await self.on_message(data)
                except Exception as e:
                    await self.on_error(e, f"Error in receiving msg: {e}, {traceback.format_exc()}")

            if heart_beat_task:
                heart_beat_task.cancel()
                await heart_beat_task


async def test():
    from utils.biliapi import WsApi
    room_id = 2516117

    async def on_message(message):
        for msg in WsApi.parse_msg(message):
            print(f"on_message: {msg}")

    async def on_connect(ws):
        print(f"on_connect: {ws}")
        await ws.send(WsApi.gen_join_room_pkg(room_id))

    async def on_shut_down():
        print(f"on_shut_down, room_id: {room_id}")

    async def on_error(e, msg):
        print(f"on_error: e: {e}, msg: {msg}")

    new_client = RCWebSocketClient(
        url=WsApi.BILI_WS_URI,
        on_message=on_message,
        on_error=on_error,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=100
    )
    await new_client.start()

    time = 0
    while True:
        time += 1
        await asyncio.sleep(2)
        print(f"Status: {new_client.status}")

        if time == 20:
            print("Kill !")
            await new_client.kill()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
