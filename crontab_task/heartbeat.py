import sys
import json
from config.log4 import crontab_task_logger as logging
import asyncio


async def post_heartbeat(cookie):
    logging.info(f"Post heartbeat for {cookie.split(';')[0]}.")

    from utils.biliapi import BiliApi
    r, data = await BiliApi.post_heartbeat_5m(cookie)
    if not r:
        logging.error(f"Post heartbeat failed! msg: {data}")
        return

    r, data = await BiliApi.post_heartbeat_last_timest(cookie)
    if not r:
        logging.error(f"Cannot post last time st! msg: {data}")
        return
    logging.info(f"Post heartbeat success!")


async def main():
    with open("data/vip_cookies.txt") as f:
        cookies = [c.strip() for c in f.readlines()]

    for c in cookies:
        await post_heartbeat(c)
        await asyncio.sleep(5)
    logging.info("Post heart beat task done.\n\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
