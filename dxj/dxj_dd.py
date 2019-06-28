import time
import logging
import asyncio
from cqhttp import CQHttp

from config import CQBOT
from utils.biliapi import WsApi, BiliApi
from utils.ws import RCWebSocketClient
from utils.dao import CookieOperator
from config.log4 import console_logger as logging

MONITOR_ROOM_ID = 13369254
bot = CQHttp(**CQBOT)


class TempData:
    __cached_user_info = {}
    gift_list_for_thank = []

    fans_id_set = None
    cache_count_limit = 10000


async def send_danmaku(msg, user=""):
    user = user or "LP"
    cookie = CookieOperator.get_cookie_by_uid(user_id=user)

    if not cookie:
        logging.error(f"Cannot get cookie for user: {user}.")
        return

    flag, msg = await BiliApi.send_danmaku(
        message=msg,
        room_id=MONITOR_ROOM_ID,
        cookie=cookie
    )
    if not flag:
        logging.error(f"Danmaku [{msg}] send failed, msg: {msg}, user: {user}.")


async def proc_message(message):
    cmd = message.get("cmd")
    if cmd.startswith("DANMU_MSG"):
        info = message.get("info", {})
        msg = str(info[1])
        uid = info[2][0]
        user_name = info[2][1]
        is_admin = info[2][2]
        ul = info[4][0]
        d = info[3]
        dl = d[0] if d else "-"
        deco = d[1] if d else "undefined"
        logging.info(f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}")

        if msg in ("总督", "提督", "舰长", "小电视"):
            await send_danmaku("|･ω･｀) ")

    elif cmd == "SEND_GIFT":
        data = message.get("data")

        uid = data.get("uid", "--")
        face = data.get("face", "")
        uname = data.get("uname", "")
        gift_name = data.get("giftName", "")
        coin_type = data.get("coin_type", "")
        total_coin = data.get("total_coin", 0)
        num = data.get("num", 0)
        price = total_coin // max(1, num)
        rnd = data.get("rnd", 0)
        created_time = data.get("timestamp", 0)

        logging.info(f"SEND_GIFT: [{coin_type.upper()}] [{uid}] [{uname}] -> {gift_name}*{num} (total_coin: {total_coin})")
        TempData.gift_list_for_thank.append([uname, gift_name, num, coin_type, created_time])

    elif cmd == "GUARD_BUY":
        data = message.get("data")

        uid = data.get("uid")
        uname = data.get("username", "")
        gift_name = data.get("gift_name", "GUARD")
        price = data.get("price", 0)
        num = data.get("num", 0)
        created_time = data.get("start_time", 0)

        logging.info(f"GUARD_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (price: {price})")
        TempData.gift_list_for_thank.append([uname, gift_name, num, "gold", created_time])


async def thank_gift():
    thank_list = {}
    need_del = []
    for e in TempData.gift_list_for_thank:
        uname, gift_name, count, coin_type, created_timestamp = e
        time_interval = time.time() - created_timestamp
        need_del.append(e)

        if time_interval < 20:
            key = f"{uname}${gift_name}"
            if key in thank_list:
                thank_list[key] += int(count)
            else:
                thank_list[key] = int(count)

    for e in need_del:
        TempData.gift_list_for_thank.remove(e)

    for key, count in thank_list.items():
        uname, gift_name = key.split("$")
        await send_danmaku(f"感谢{uname}赠送的{count}个{gift_name}! 大气大气~")
        logging.info(f"DEBUG: gift_list_for_thank length: {len(TempData.gift_list_for_thank)}, del: {len(need_del)}")


async def main():
    async def on_connect(ws):
        logging.info("connected.")
        await ws.send(WsApi.gen_join_room_pkg(MONITOR_ROOM_ID))

    async def on_shut_down():
        logging.error("shutdown!")
        raise RuntimeError("Connection broken!")

    async def on_message(message):
        for m in WsApi.parse_msg(message):
            try:
                await proc_message(m)
            except Exception as e:
                logging.error(f"Error happened when proc_message: {e}", exc_info=True)

    new_client = RCWebSocketClient(
        url=WsApi.BILI_WS_URI,
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()
    logging.info("Hansy ws stated.")

    counter = -1
    while True:
        await asyncio.sleep(1)
        counter = (counter + 1) % 10000000000

        if counter % 15 == 0:
            await thank_gift()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
