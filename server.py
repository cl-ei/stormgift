import time
import asyncio
import websockets

from config import PRIZE_HANDLER_SERVE_ADDR, PRIZE_SOURCE_PUSH_ADDR


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
            print("Ws message received: %s" % m)
            if m == "heart beat":
                print("set heart beat time.")
                ws.last_active_time = time.time()

        if not task.cancelled():
            task.cancel()
        if ws in self.__clients:
            self.__clients.remove(ws)
            print("Client leave: %s, current connections: %s" % (ws, len(self.__clients)))

    def serve(self):
        return websockets.serve(self.handler, self.host, self.port)

    async def notice_all(self, msg):
        lived_clients = [c for c in self.__clients if not c.closed]
        print("Lived clients: %s" % len(lived_clients))
        for c in lived_clients:
            if not c.closed:
                await c.send(msg)


class PrizeInfoReceiver(asyncio.protocols.BaseProtocol):
    notice_handler = None

    def __init__(self):
        super(PrizeInfoReceiver, self).__init__()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        message = data.decode()
        if self.__class__.notice_handler:
            asyncio.gather(self.__class__.notice_handler.notice_all(message))


async def main():
    h = NoticeHandler(*PRIZE_HANDLER_SERVE_ADDR)
    await h.serve()
    print("Notice handler started.")
    PrizeInfoReceiver.notice_handler = h
    await loop.create_datagram_endpoint(PrizeInfoReceiver, local_addr=PRIZE_SOURCE_PUSH_ADDR)
    print("Price info acceptor started.")
    while True:
        await asyncio.sleep(5)
        # print("*"*20)
        # for task in asyncio.all_tasks():
        #     print(task)
        # print("*" * 20)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.run_forever()
