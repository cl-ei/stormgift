import time
import asyncio
import websockets

cnt = 0


class NoticeHandler(object):
    def __init__(self):
        self.__clients = set()

    async def handler(self, ws, path):
        self.__clients.add(ws)

        async def wait_timeout():
            while not ws.closed:
                await asyncio.sleep(10)
                if time.time() - getattr(ws, "last_active_time", 0) > 10:
                    print("close it!")
                    await ws.close()

        task = asyncio.get_event_loop().create_task(wait_timeout())

        while not ws.closed:
            try:
                m = await ws.recv()
            except Exception:
                print("close")
                break

            print("receive: %s" % m)
            if m == "heart beat":
                ws.last_active_time = time.time()
                print("ws last_active_time set: %s" % ws.last_active_time)

        if not task.cancelled():
            task.cancel()
        print("--")
        if ws in self.__clients:
            self.__clients.remove(ws)

    def serve(self):
        return websockets.serve(self.handler, 'localhost', 8765)

    async def notice_all(self, msg):
        for c in self.__clients:
            if not c.closed:
                print(c)
                await c.send(msg)


h = NoticeHandler()


async def mo():
    await asyncio.sleep(5)
    await h.notice_all("123")


async def main():
    await h.serve()

loop = asyncio.get_event_loop()
asyncio.gather(main(), mo())
loop.run_forever()
