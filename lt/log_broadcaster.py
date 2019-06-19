import asyncio
import websockets
from config.log4 import console_logger as logging


class LogBroadcaster(object):
    def __init__(self, host, port):
        self.__clients = set()
        self.host = host
        self.port = port

    async def handler(self, ws, path):
        self.__clients.add(ws)
        logging.info(
            f"New client connected: ({ws.host}, {ws.port}), "
            f"path: {path}, current conn: {len(self.__clients)}"
        )

        while not ws.closed:
            await asyncio.sleep(10)

        if ws in self.__clients:
            self.__clients.remove(ws)
            logging.info("Client leave: %s, current connections: %s" % (ws, len(self.__clients)))

    def start_server(self):
        return websockets.serve(self.handler, self.host, self.port)

    async def notice_all(self, msg):
        lived_clients = [c for c in self.__clients if not c.closed]
        logging.info(f"Notice to all, msg: [{msg}], Lived clients: {len(lived_clients)}")
        for c in lived_clients:
            try:
                await c.send(msg)
            except Exception as e:
                print(f"Exception at send notice: {e}")


async def main():
    server = LogBroadcaster("127.0.0.1", 8072)
    await server.start_server()
    logging.info(f"Server started.")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
