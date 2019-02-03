import asyncio
from random import random
from math import floor
import websockets


class WsApi(object):
    BILI_WS_URI = "ws://broadcastlv.chat.bilibili.com:2244/sub"
    PACKAGE_HEADER_LENGTH = 16
    CONST_MESSAGE = 7
    CONST_HEART_BEAT = 2

    @classmethod
    def generate_packet(cls, action, payload=""):
        payload = payload.encode("utf-8")
        packet_length = len(payload) + cls.PACKAGE_HEADER_LENGTH
        buff = bytearray(cls.PACKAGE_HEADER_LENGTH)
        # package length
        buff[0] = (packet_length >> 24) & 0xFF
        buff[1] = (packet_length >> 16) & 0xFF
        buff[2] = (packet_length >> 8) & 0xFF
        buff[3] = packet_length & 0xFF
        # migic & version
        buff[4] = 0
        buff[5] = 16
        buff[6] = 0
        buff[7] = 1
        # action
        buff[8] = 0
        buff[9] = 0
        buff[10] = 0
        buff[11] = action
        # migic parma
        buff[12] = 0
        buff[13] = 0
        buff[14] = 0
        buff[15] = 1
        return bytes(buff + payload)

    @classmethod
    def gen_heart_beat_pkg(cls):
        return cls.generate_packet(cls.CONST_HEART_BEAT)

    @classmethod
    def gen_join_room_pkg(cls, room_id):
        uid = int(1E15 + floor(2E15 * random()))
        package = '{"uid":%s,"roomid":%s}' % (uid, room_id)
        return cls.generate_packet(cls.CONST_MESSAGE, package)


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
                print("reconnect ...")
        self._reconnect_cb = reconnect_cb

        def exc_handler(*rags, **kw):
            print("----<>", *rags, **kw)
            loop = asyncio.get_running_loop()
            print("h: %s" % loop.get_exception_handler())

        loop = asyncio.get_running_loop()
        loop.set_exception_handler(exc_handler)

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


async def main():
    async def on_connect():
        print("Connected!")

    async def on_shut_down(*args):
        print("dfasfasf")

    async def on_connect(ws):
        print("on_connect")
        await ws.send(WsApi.gen_join_room_pkg(478948))

    async def on_shut_down():
        print("shut done! %s, area: %s" % (4424139, 23))

    async def on_message(bin_msg):
        print("Received: %s" % bin_msg)

    new_client = ReConnectingWsClient(
        uri=WsApi.BILI_WS_URI,  # "ws://localhost:22222",
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()
    print("Stated")
    while True:
        await asyncio.sleep(5)


loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.gather( main()))
loop.run_forever()
