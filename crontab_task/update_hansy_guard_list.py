import asyncio
from utils.biliapi import BiliApi
from config.log4 import crontab_task_logger as logging


async def update_hansy_guard_list():
    guard_list = await BiliApi.get_guard_list(uid=65568410)
    if not guard_list:
        logging.error("update_hansy_guard_list FAILED!")
        return

    text = "\n".join([
        "".join([" ❤ " + _["name"] for _ in guard_list if _["level"] < 3]),
        "".join([" ❤ " + _["name"] for _ in guard_list if _["level"] == 3])
    ])

    with open("data/hansy_guard_list.txt", "wb") as f:
        f.write(text.encode("utf-8"))


loop = asyncio.get_event_loop()
loop.run_until_complete(update_hansy_guard_list())
