import re
import os
import sys
import asyncio
import time
from random import choice, random
import requests
import json
from utils.ws import ReConnectingWsClient
from utils.biliapi import WsApi, BiliApi
import logging

if "linux" in sys.platform:
    from config import config
    LOG_PATH = config["LOG_PATH"]
else:
    LOG_PATH = "./log"

log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
file_handler = logging.FileHandler(os.path.join(LOG_PATH, "hansy.log"), encoding="utf-8")
file_handler.setFormatter(log_format)

logger = logging.getLogger("hansy")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)
logger.addHandler(file_handler)
logging = logger


MONITOR_ROOM_ID = 2516117

RECORDER_UID = 39748080
DADUN_UID = 20932326
HANSY_MSG_INTERVAL = 120
HANSY_MSG_LIST = [
    # "📢 一定要来网易云关注「管珩心」哦，超多高质量单曲等你来听~",
    "📢 主播千万个，泡泡就一个~  听歌不关注，下播两行泪(‘；ω；´) ",
    "📢 喜欢泡泡的小伙伴，加粉丝群436496941来玩耍呀~",
    "📢 更多好听的原创歌和翻唱作品，网易云音乐搜索「管珩心」~",
    "📢 你的关注和弹幕是直播的动力，小伙伴们多粗来聊天掰头哇~",
    "📢 赠送1个B坷垃，就可以领取珩心专属「电磁泡」粉丝勋章啦~",
    "📢 有能力的伙伴上船支持一下主播鸭~还能获赠纪念礼品OvO",
]
LAST_ACTIVE_TIME = time.time() - HANSY_MSG_INTERVAL*len(HANSY_MSG_LIST) - 1


def master_is_active():
    result = time.time() - LAST_ACTIVE_TIME < len(HANSY_MSG_LIST)*HANSY_MSG_INTERVAL
    return result


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


async def send_hansy_danmaku(msg):
    flag, cuid, cookie = await load_cookie()
    if not flag:
        logging.error("Bad cookie!")
        return
    await BiliApi.send_danmaku(msg, room_id=MONITOR_ROOM_ID, cookie=cookie)


async def send_recorder_group_danmaku():
    flag, cuid, cookie = await load_cookie(12)
    if not flag:
        logging.error("Bad cookie!")
        return
    await BiliApi.enter_room(MONITOR_ROOM_ID, cookie)

    if master_is_active():
        await BiliApi.send_danmaku("📢 想要观看直播回放的小伙伴，记得关注我哦~", room_id=MONITOR_ROOM_ID, cookie=cookie)


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
        dl = d[0] if d else "-"
        deco = d[1] if d else "undefined"
        logging.info(f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}")

        if str(msg).startswith("📢"):
            return

        global LAST_ACTIVE_TIME
        LAST_ACTIVE_TIME = time.time()

        if uid == DADUN_UID:
            return

        elif uid == 65981801:  # 大连
            if "心" in msg or "美" in msg or "好" in msg or random() > 0.8:
                await send_hansy_danmaku(choice([
                    "🤖 大连你竟然连童子鸡🐔都不放过！",
                    "🤖 大连，等身抱枕只会在你的梦里~快去睡吧晚安安~",
                    "🤖 大连你个大居蹄子！",
                    "🤖 大连，你的舌头没救了……切了吧",
                    "🤖 没想到你是这样的大连！（￣へ￣）",
                ]))
        else:
            if "好听" in msg and random() > 0.7:
                await send_hansy_danmaku(choice([
                    "🤖 φ(≧ω≦*)♪好听好听！ 打call ᕕ( ᐛ )ᕗ",
                    "🤖 好听！给跪了! ○|￣|_ (这么好听还不摁个关注？！",
                    "🤖 好听! 我的大仙泡最美最萌最好听 ´･∀･)乂(･∀･｀",
                    "🤖 觉得好听的话，就按个关注别走好吗…(๑˘ ˘๑) ♥",
                ]))

            if "点歌" in msg and "吗" in msg:
                await send_hansy_danmaku("🤖 可以点歌哦，等这首唱完直接发歌名就行啦╰(*°▽°*)╯")

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
            logging.info(f"SEND_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (total_coin: {total_coin})")

    elif cmd == "COMBO_END":
        data = message.get("data")
        uname = data.get("uname", "")
        gift_name = data.get("gift_name", "")
        price = data.get("price")
        count = data.get("combo_num", 0)
        logging.info(f"GOLD_GIFT: [ ----- ] [{uname}] -> {gift_name}*{count} (price: {price})")

    elif cmd == "GUARD_BUY":
        data = message.get("data")
        uid = data.get("uid")
        uname = data.get("username", "")
        gift_name = data.get("gift_name", "GUARD")
        price = data.get("price")
        num = data.get("num", 0)
        logging.info(f"GUARD_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (price: {price})")


async def main():
    async def on_connect(ws):
        logging.info("connected.")
        await ws.send(WsApi.gen_join_room_pkg(MONITOR_ROOM_ID))

    async def on_shut_down():
        logging.error("shutdown!")
        raise RuntimeError("Connection broken!")

    async def on_message(message):
        for m in WsApi.parse_msg(message):
            await proc_message(m)

    new_client = ReConnectingWsClient(
        uri=WsApi.BILI_WS_URI,
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()
    logging.info("Hansy ws stated.")

    counter = 0
    hansy_msg_index = 0
    while True:
        await asyncio.sleep(1)
        counter += 1
        if counter > 10000*len(HANSY_MSG_LIST):
            counter = 0

        if counter % int(HANSY_MSG_INTERVAL) == 0:
            if master_is_active():
                msg = HANSY_MSG_LIST[hansy_msg_index]
                await send_hansy_danmaku(msg)

                hansy_msg_index += 1
                if hansy_msg_index == len(HANSY_MSG_LIST):
                    hansy_msg_index = 0

        if counter % (60*5) == 0:
            await send_recorder_group_danmaku()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
