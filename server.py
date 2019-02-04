import time
import asyncio
import websockets

from config import config

PRIZE_HANDLER_SERVE_ADDR = tuple(config["PRIZE_HANDLER_SERVE_ADDR"])
PRIZE_SOURCE_PUSH_ADDR = tuple(config["PRIZE_SOURCE_PUSH_ADDR"])


class NoticeHandler(object):
    def __init__(self, host, port):
        self.__clients = set()
        self.host = host
        self.port = port

    async def handler(self, ws, path):
        self.__clients.add(ws)
        print("New client connected: (%s, %s), path: %s" % (ws.host, ws.port, path))
        print("Current connections: %s" % len(self.__clients))
        ws.last_active_time = time.time()

        async def wait_timeout():
            while not ws.closed:
                await asyncio.sleep(10)
                time_delta = time.time() - getattr(ws, "last_active_time", 0)
                if time_delta > 25:
                    print("Heart beat time out: %s. close it!" % time_delta)
                    await ws.close()

        task = asyncio.create_task(wait_timeout())

        while not ws.closed:
            try:
                m = await ws.recv()
            except Exception as e:
                print("Exception on receiving: %s. close it." % e)
                break

            if type(m) == bytes:
                m = m.decode()
            if m == "heart beat":
                ws.last_active_time = time.time()

        if not task.cancelled():
            task.cancel()
        if ws in self.__clients:
            self.__clients.remove(ws)
            print("Client leave: %s, current connections: %s" % (ws, len(self.__clients)))

    def start_server(self):
        return websockets.serve(self.handler, self.host, self.port)

    async def notice_all(self, msg):
        lived_clients = [c for c in self.__clients if not c.closed]
        print(f"Notice to all, msg: [{msg}], Lived clients: {len(lived_clients)}")
        for c in lived_clients:
            await c.send(msg)


class PrizeInfoReceiver:
    notice_handler = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, message, addr):
        print(f"Message received from udp server: [{message}]")
        if self.__class__.notice_handler:
            asyncio.gather(self.__class__.notice_handler(message))

    @classmethod
    async def start_server(cls):
        listen = loop.create_datagram_endpoint(cls, local_addr=('127.0.0.1', 11111))
        await asyncio.ensure_future(listen)


async def main():
    h = NoticeHandler(*PRIZE_HANDLER_SERVE_ADDR)

    PrizeInfoReceiver.notice_handler = h.notice_all
    await PrizeInfoReceiver.start_server()
    await h.start_server()
    print(f"Server started.")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.run_forever()
