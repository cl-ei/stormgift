import asyncio
from utils.biliapi import BiliApi
from lt import LtGiftMessageQ
from config.log4 import lt_source_logger as logging


async def main():
    flag, r = await BiliApi.get_guard_room_list()
    if not flag:
        logging.error(f"Cannot find guard room. r: {r}")
        return

    for room_id in r:
        await asyncio.sleep(1)
        await LtGiftMessageQ.post_gift_info("G", room_id)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

