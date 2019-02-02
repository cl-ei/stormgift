import json
import asyncio
import aiohttp
import traceback

from config import PRIZE_HANDLER_SERVE_ADDR
from utils.ws import ReConnectingWsClient
from utils.biliapi import BiliApi


class ClientManager(object):
    def __init__(self):
        self.__rws_clients = {}

    @staticmethod
    async def search_new_room(old_room_id, area):
        return await BiliApi.search_live_room(area, old_room_id)

    async def run(self):
        print(await BiliApi.check_live_status(40195, 5))
        for i in range(7):
            await self.search_new_room(None, i)

        while True:
            await asyncio.sleep(1)


async def main():
    m = ClientManager()
    await m.run()

    # await asyncio.sleep(5)
    #
    # async def s(): return 0
    # await c.stop()
    #
    # await asyncio.sleep(10)
    # await c.kill(s)

    while True:
        await asyncio.sleep(3)
        print("*" * 80)
        for _ in asyncio.all_tasks():
            print(_)
        print("*"*80)
        # await m.get_clients_info()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
