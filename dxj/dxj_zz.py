import time
import logging
import asyncio
from config import g
from utils.cq import async_zy
from utils.biliapi import WsApi
from utils.ws import RCWebSocketClient
from config.log4 import console_logger as logging
from utils.dao import redis_cache


MONITOR_ROOM_ID = 2951931
last_live_time = 0


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
        global last_live_time
        now = time.time()
        if now - last_live_time < 5:
            return
        last_live_time = now
        await async_zy.send_private_msg(
            user_id=g.QQ_NUMBER_DD,
            message=f"温柔祯开播了.\n\nhttps://live.bilibili.com/{MONITOR_ROOM_ID}"
        )

        key = "LT_ZZ_LIVE_NOTICE_LIVE"
        if await redis_cache.set_if_not_exists(key=key, value="123", timeout=60*30):
            await async_zy.send_group_msg(
                group_id=g.QQ_NUMBER_温柔祯,
                message=f"温柔祯开播啦\n\nhttps://live.bilibili.com/{MONITOR_ROOM_ID}"
            )

    elif cmd == "PREPARING":
        await async_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message="温柔祯已下播。")

        key = "LT_ZZ_LIVE_NOTICE_PREPARING"
        if await redis_cache.set_if_not_exists(key=key, value="123", timeout=60*30):
            await async_zy.send_group_msg(group_id=g.QQ_NUMBER_温柔祯, message="温柔祯已下播。")


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
