import json
import asyncio
import websockets
from config import PRIZE_HANDLER_SERVE_ADDR


class ReconnectedWsClient(object):
    def __init__(self, host, port, on_message):
        self.retry_times = 0
        self.server_uri = f"ws://{host}:{port}"
        self.on_message = on_message

    async def start(self):
        try:
            await asyncio.create_task(self._create_client())
        except Exception as e:
            print(e)

        self.retry_times += 1
        if self.retry_times < 3:
            sleep = 0.1
        elif self.retry_times < 10:
            sleep = 0.5
        elif self.retry_times < 20:
            sleep = 2
        else:
            sleep = 5
        await asyncio.sleep(sleep)
        await self.start()

    async def _create_client(self):
        async with websockets.connect(self.server_uri) as ws:
            print("Notice server connected.")
            self.retry_times = 0

            async def send_heart_beat():
                while not ws.closed:
                    await asyncio.sleep(5)
                    try:
                        await ws.send("heart beat")
                    except Exception as e:
                        print("Error in send heart beat e: %s" % e)
                        return
            heart_beat_task = asyncio.create_task(send_heart_beat())

            while not ws.closed:
                try:
                    data = await ws.recv()
                    print("Ws received: %s" % data)
                    await self.on_message(data)
                except Exception as e:
                    print("Error in receiving msg: %s" % e)
                    break
            heart_beat_task.cancel()
        print("Notice Server disconnected.")


class Acceptor(object):
    def __init__(self):
        self.q = asyncio.Queue(maxsize=2000)
        self.cookie_file = "data/cookie.json"

    async def add_task(self, key):
        await self.q.put(key)

    async def load_cookie(self):
        with open(self.cookie_file, "r") as f:
            c = json.load(f)
        return c["RAW_COOKIE_LIST"], c["BLACK_LIST"]

    async def accept_tv(self, i, cookie):
        print("i: %s, c: %s" % (i, cookie))

    async def accept_guard(self, i, cookie):
        print("i: %s, c: %s" % (i, cookie))

    async def accept_prize(self, key):
        if key.startswith("_T"):
            proc_fn = self.accept_tv
        elif key.startswith("NG"):
            proc_fn = self.accept_guard
        else:
            return

        cookies, black_list = await self.load_cookie()
        for i in range(len(cookies)):
            if i not in black_list:
                await proc_fn(i, cookies[i])
                await asyncio.sleep(0.5)

    async def run(self):
        while True:
            r = await self.q.get()
            await self.accept_prize(r)


async def main():
    a = Acceptor()
    acceptor_task = asyncio.create_task(a.run())

    async def on_price_message(key):
        await a.add_task(key)

    c = ReconnectedWsClient("129.204.43.2", 11112, on_message=on_price_message)  # *PRIZE_HANDLER_SERVE_ADDR)
    await c.start()
    await acceptor_task


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
