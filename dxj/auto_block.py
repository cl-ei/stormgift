import logging
import asyncio
from utils.ws import RCWebSocketClient
from utils.biliapi import WsApi, BiliApi
from utils.highlevel_api import DBCookieOperator
from config.log4 import console_logger as logging

MONITOR_ROOM_ID = 4063935


async def get_cookie(user="DD"):
    user_cookie_obj = await DBCookieOperator.get_by_uid(user)
    return user_cookie_obj.cookie if user_cookie_obj else ""


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
        if not is_admin:
            return

        # if msg[0] == "R":
        #     try:
        #         uid = int(msg[1:].strip(), 16)
        #     except (ValueError, IndexError, TypeError):
        #         return

    elif cmd.startswith("ROOM_BLOCK_MSG"):
        # {
        # 'cmd': 'ROOM_BLOCK_MSG',
        # 'uid': '473518981',
        # 'uname': '劳c挡焙岸',
        # 'data': {
        #       'uid': '473518981',
        #       'uname': '劳c挡焙岸',
        #       'operator': 1
        # },
        # 'roomid': 4063935
        # }
        cookie = await get_cookie("DD")
        roomid = 2516117
        user_id = int(danmaku["uid"])
        await BiliApi.block_user(cookie, roomid, user_id)

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
