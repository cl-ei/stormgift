import re
import os
import sys
import asyncio
import requests
import json
from utils.ws import ReConnectingWsClient
from utils.biliapi import WsApi, BiliApi
import logging

if "linux" in sys.platform:
    LOG_PATH = "/home/wwwroot/log"
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


class DanmakuSetting:
    MONITOR_ROOM_ID = 11472492
    ROBOT_ON = False


class TempData:
    silver_gift_list = []


async def get_tuling_response(msg):
    api_key = "c83e8c03c71d43b6b0ce271d485896d8"
    url = "http://openapi.tuling123.com/openapi/api/v2"
    req_json = {
        "reqType": 0,
        "perception": {"inputText": {"text": msg}},
        "userInfo": {
            "apiKey": api_key,
            "userId": 248138,
        }
    }
    try:
        r = requests.post(url=url, json=req_json)
        if r.status_code != 200:
            raise Exception(f"Bad status code: {r.status_code}")
        r = json.loads(r.text)
        msg = r.get("results", [])[0].get("values", {}).get("text", "")
    except Exception as e:
        return False, ""
    return bool(msg), msg


async def send_danmaku(msg):
    try:
        from data import COOKIE_DD
    except Exception as e:
        logging.error(f"Cannot load cookie, e: {e}.", exc_info=True)
        return

    await BiliApi.send_danmaku(
        message=msg,
        room_id=DanmakuSetting.MONITOR_ROOM_ID,
        cookie=COOKIE_DD
    )


async def proc_message(message):
    cmd = message.get("cmd")
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

        if DanmakuSetting.ROBOT_ON:
            if is_admin and msg == "关闭聊天":
                DanmakuSetting.ROBOT_ON = False
                return await send_danmaku("聊天功能已关闭。房管发送「开启聊天」可以再次打开。")

            from data import UID_DD
            if uid == UID_DD:
                return

            flag, msg = await get_tuling_response(msg)
            if flag:
                msg = f"{user_name}　{msg}"
                await send_danmaku(msg[:30])
                if len(msg) > 30:
                    if len(msg) > 60:
                        msg = msg[30:55] + "..."
                    else:
                        msg = msg[30:60]
                    await asyncio.sleep(0.4)
                    await send_danmaku(msg)
        else:
            if is_admin and msg == "开启聊天":
                DanmakuSetting.ROBOT_ON = True
                return await send_danmaku("聊天功能已开启。房管发送「关闭聊天」即可关闭。")

    elif cmd == "SEND_GIFT":
        data = message.get("data")
        uid = data.get("uid", "--")
        face = data.get("face", "")
        uname = data.get("uname", "")
        gift_name = data.get("giftName", "")
        coin_type = data.get("coin_type", "")
        total_coin = data.get("total_coin", 0)
        num = data.get("num", "")
        if coin_type != "gold":
            TempData.silver_gift_list.append(f"{uname}${gift_name}${num}")

    elif cmd == "COMBO_END":
        data = message.get("data")
        uname = data.get("uname", "")
        gift_name = data.get("gift_name", "")
        price = data.get("price")
        count = data.get("combo_num", 0)
        await send_danmaku(f"感谢{uname}赠送的{count}个{gift_name}! 大气大气~")

    elif cmd == "GUARD_BUY":
        data = message.get("data")
        uid = data.get("uid")
        uname = data.get("username", "")
        gift_name = data.get("gift_name", "GUARD")
        price = data.get("price")
        num = data.get("num", 0)
        await send_danmaku(f"感谢{uname}开通了{num}个月的{gift_name}! 大气大气~")


async def main():
    async def on_connect(ws):
        logging.info("on_connect")
        await ws.send(WsApi.gen_join_room_pkg(DanmakuSetting.MONITOR_ROOM_ID))

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
    logging.info("Stated.")
    while True:
        gift_list = {}
        while TempData.silver_gift_list:
            gift = TempData.silver_gift_list.pop()
            uname, gift_name, num = gift.split("$")
            key = f"{uname}${gift_name}"
            if key in gift_list:
                gift_list[key] += int(num)
            else:
                gift_list[key] = int(num)

        if gift_list:
            for key, num in gift_list.items():
                uname, gift_name = key.split("$")
                await send_danmaku(f"感谢{uname}赠送的{num}个{gift_name}! 大气大气~")
        await asyncio.sleep(10)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
