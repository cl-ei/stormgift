import time
import asyncio
from utils.biliapi import BiliApi
from config.log4 import crontab_task_logger as logging


async def main():
    logging.info(f"Start do sign task.")
    start_time = time.time()

    with open("data/valid_cookies.txt") as f:
        cookies = [_.strip() for _ in f.readlines()]

    for index, cookie in enumerate(cookies):
        await asyncio.sleep(0.5)
        await BiliApi.do_sign(cookie)

        await asyncio.sleep(0.5)
        r, data = await BiliApi.do_sign_group(cookie)
        if not r:
            logging.error(f"Sign group failed, {index}-{cookie.split(';')[0]}: {data}")

        await asyncio.sleep(0.5)
        await BiliApi.do_sign_double_watch(cookie)

        if "20932326" in cookie:
            await asyncio.sleep(0.5)
            await BiliApi.silver_to_coin(cookie)

    logging.info(f"Do sign task done. cost: {int((time.time() - start_time) *1000)} ms.\n\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

