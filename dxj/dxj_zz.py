import logging
import asyncio
from config import g
from utils.cq import async_zy
from utils.ws import RCWebSocketClient
from utils.biliapi import WsApi, BiliApi
from config.log4 import console_logger as logging
from utils.highlevel_api import DBCookieOperator


MONITOR_ROOM_ID = 2951931


async def send_danmaku(msg):
    user = "DD"
    c = await DBCookieOperator.get_by_uid(user_id=user)
    if not c:
        logging.error(f"Cannot get cookie for user: {user}.")
        return

    while True:
        send_m = msg[:30]
        for _ in range(3):
            flag, data = await BiliApi.send_danmaku(message=send_m, room_id=MONITOR_ROOM_ID, cookie=c.cookie)
            if flag:
                if data == "fire":
                    return

                logging.info(f"DMK success: {send_m}, reason: {data}")
                break
            else:
                if "账号未登录" in data:
                    await DBCookieOperator.add_cookie_by_account(account=c.account, password=c.password)
                    continue
                logging.error(f"Dmk send failed, msg: {send_m}, reason: {data}")
                await asyncio.sleep(0.4)
        else:
            logging.error(f"Cannot send danmaku {send_m}. now return.")
            return

        msg = msg[30:]
        if msg:
            await asyncio.sleep(1.1)
        else:
            return


async def proc_message(message):
    cmd = message.get("cmd", "")
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
        msg_record = f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}"
        logging.info(msg_record)

    elif cmd == "LIVE":
        await async_zy.send_private_msg(
            user_id=g.QQ_NUMBER_DD,
            message=f"温柔祯开播了.\n\nhttps://live.bilibili.com/{MONITOR_ROOM_ID}"
        )

    elif cmd == "PREPARING":
        await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message="温柔祯已下播。")


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
        heart_beat_interval=30
    )

    await new_client.start()

    logging.info("ZZ ws stated.")
    while True:
        await asyncio.sleep(10)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
