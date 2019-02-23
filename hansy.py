import re
import os
import sys
import asyncio
import requests
import json
from utils.ws import ReConnectingWsClient
from utils.biliapi import WsApi, BiliApi
import logging

from config import config
if "linux" in sys.platform:
    LOG_PATH = config["LOG_PATH"]
else:
    LOG_PATH = "./log"

log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
xk_file_handler = logging.FileHandler(os.path.join(LOG_PATH, "xiaoke.log"))
xk_file_handler.setFormatter(log_format)

logger = logging.getLogger("xk")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)
logger.addHandler(xk_file_handler)
logging = logger


MONITOR_ROOM_ID = 280446
SILVER_GIFT_LIST = []


async def load_cookie(index=0):
    try:
        with open("data/cookie.json", "r") as f:
            cookies = json.load(f)
        cookie = cookies.get("RAW_COOKIE_LIST")[index]
    except Exception as e:
        cookie = ""
    user_ids = re.findall(r"DedeUserID=(\d+)", cookie)
    if not user_ids:
        return False, None, None

    uid = int(user_ids[0])
    return True, uid, cookie


async def proc_message(message):
    cmd = message.get("cmd")
    print(f"{json.dumps(message, ensure_ascii=False)}")
    if cmd == "DANMU_MSG":
        info = message.get("info", {})
        msg = info[1]
        uid = info[2][0]
        user_name = info[2][1]
        is_admin = info[2][2]
        ul = info[4][0]
        d = info[3]
        dl = d[0] if d else "0"
        deco = d[1] if d else "^^"
        logging.info(f"{'[管]' if is_admin else ''}[{uid}] [{user_name}][{ul}] [{deco} {dl}]-> {msg}")
    #
    # elif cmd == "SEND_GIFT":
    #     data = message.get("data")
    #     uid = data.get("uid", "--")
    #     face = data.get("face", "")
    #     uname = data.get("uname", "")
    #     gift_name = data.get("giftName", "")
    #     coin_type = data.get("coin_type", "")
    #     total_coin = data.get("total_coin", 0)
    #     num = data.get("num", "")
    #     if coin_type != "gold":
    #         SILVER_GIFT_LIST.append(f"{uname}${gift_name}${num}")
    #
    # elif cmd == "COMBO_END":
    #     data = message.get("data")
    #     uname = data.get("uname", "")
    #     gift_name = data.get("gift_name", "")
    #     price = data.get("price")
    #     count = data.get("combo_num", 0)
    #     flag, cuid, cookie = await load_cookie()
    #     if not flag:
    #         return
    #     await BiliApi.send_danmaku(f"感谢{uname}赠送的{count}个{gift_name}! 大气大气~", room_id=MONITOR_ROOM_ID, cookie=cookie)
    #
    # elif cmd == "GUARD_BUY":
    #     data = message.get("data")
    #     uid = data.get("uid")
    #     uname = data.get("username", "")
    #     gift_name = data.get("gift_name", "GUARD")
    #     price = data.get("price")
    #     num = data.get("num", 0)
    #
    #     flag, cuid, cookie = await load_cookie()
    #     if not flag:
    #         return
    #     await BiliApi.send_danmaku(f"感谢{uname}开通了{num}个月的{gift_name}! 大气大气~", room_id=MONITOR_ROOM_ID, cookie=cookie)


async def thank_silver_gift():
    gift_list = {}
    while SILVER_GIFT_LIST:
        gift = SILVER_GIFT_LIST.pop()
        uname, gift_name, num = gift.split("$")
        key = f"{uname}${gift_name}"
        if key in gift_list:
            gift_list[key] += int(num)
        else:
            gift_list[key] = int(num)

    if gift_list:
        for key, num in gift_list.items():
            flag, cuid, cookie = await load_cookie()
            if not flag:
                return
            uname, gift_name = key.split("$")
            await BiliApi.send_danmaku(
                f"感谢{uname}赠送的{num}个{gift_name}! 大气大气~",
                room_id=MONITOR_ROOM_ID,
                cookie=cookie
            )


async def main():
    async def on_connect(ws):
        logging.info("on_connect")
        await ws.send(WsApi.gen_join_room_pkg(MONITOR_ROOM_ID))

    async def on_shut_down():
        logging.error("shut done!")

    async def on_message(message):
        for msg in WsApi.parse_msg(message):
            await proc_message(msg)

    new_client = ReConnectingWsClient(
        uri=WsApi.BILI_WS_URI,  # "ws://localhost:22222",
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()
    logging.info("Hansy ws stated.")
    while True:
        # await thank_silver_gift()
        await asyncio.sleep(8)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
