import sys
import json
import logging
import asyncio

VIP_LIST = [
    "DedeUserID=20932326",
    "DedeUserID=312186483",
    "DedeUserID=49279889",
    "DedeUserID=87301592",
    "DedeUserID=48386500",
    "DedeUserID=95284802",
    "DedeUserID=39748080",
    "DedeUserID=359496014",
]


log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
logger = logging.getLogger("heartbeat")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)

if "linux" in sys.platform:
    file_handler = logging.FileHandler("/home/wwwroot/log/heartbeat.log")
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

logging = logger


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
    if "linux" in sys.platform:
        sys.path.append('/home/wwwroot/stormgift/')

    else:
        sys.path.append('../')

    with open("/home/wwwroot/stormgift/data/cookie.json") as f:
        cookies = json.load(f).get("RAW_COOKIE_LIST", []) or []

    for c in cookies:
        is_vip = False
        for v in VIP_LIST:
            if c.startswith(v):
                is_vip = True
                break
        if is_vip:
            await post_heartbeat(c)
            await asyncio.sleep(5)
    logging.info("Post heart beat task done.\n\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
