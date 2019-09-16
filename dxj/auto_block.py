import logging
import asyncio
from utils.ws import RCWebSocketClient
from utils.biliapi import WsApi, BiliApi
from utils.highlevel_api import DBCookieOperator
from config.log4 import console_logger as logging

MONITOR_ROOM_ID = 4063935


async def get_cookie(user="LP"):
    user_cookie_obj = await DBCookieOperator.get_by_uid(user)
    return user_cookie_obj.cookie if user_cookie_obj else ""


async def send_danmaku(msg, user=""):
    if not user:
        user = "LP"
    cookie = await get_cookie(user)

    if not cookie:
        logging.error(f"Cannot get cookie for user: {user}.")
        return

    flag, err_msg = await BiliApi.send_danmaku(
        message=msg,
        room_id=MONITOR_ROOM_ID,
        cookie=cookie
    )
    if flag:
        logging.info(f"Danmaku [{msg}] sent, msg: {err_msg}, user: {user}.")
    else:
        logging.error(f"Danmaku [{msg}] send failed, msg: {err_msg}, user: {user}.")


async def proc_danmaku(danmaku):
    cmd = danmaku.get("cmd")
    if cmd.startswith("DANMU_MSG"):
        info = danmaku.get("info", {})
        msg = str(info[1])
        uid = info[2][0]
        user_name = info[2][1]
        is_admin = info[2][2]
        ul = info[4][0]
        d = info[3]
        dl = d[0] if d else "-"
        deco = d[1] if d else "undefined"
        logging.info(f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}")
        return

    print(danmaku)


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
                await proc_danmaku(m)
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
    logging.info("Ws stated.")

    while True:
        await asyncio.sleep(1)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
