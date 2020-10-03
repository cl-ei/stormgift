import time
import datetime
import logging
import asyncio
import aiohttp
from utils.cq import qq_yk
from utils.biliapi import WsApi
from utils.ws import RCWebSocketClient
from config.log4 import console_logger as logging
from utils.dao import redis_cache
from src.api.bili import BiliPublicApi


MONITOR_ROOM_ID = 92450
QQ_GROUP_ID = 1013933390
last_live_time = 0


async def get_live_msg() -> str:
    api = BiliPublicApi()
    info = await api.get_live_room_detail(MONITOR_ROOM_ID)
    key_frame = info.keyframe
    try:
        async with aiohttp.request("get", key_frame) as resp:
            assert resp.status == 200
            content = await resp.read()
            assert content
    except Exception as e:
        _ = e
        return f"土豆开剥辣！\n\nhttps://live.bilibili.com/612"

    file_name = f"/home/wwwroot/qq_yk/images/LY_{datetime.datetime.now()}.jpg"
    with open(file_name, "wb") as f:
        f.write(content)

    return (
        f"土豆开剥辣，快来围观ε=ε=(ノ≧∇≦)ノ\n\n"
        f"标题：{info.title}\n"
        f"https://live.bilibili.com/612"
        f"[CQ:image,file={file_name}]"
    )


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

        key = "LT_LY_LIVE_NOTICE_LIVE"
        if await redis_cache.set_if_not_exists(key=key, value="123", timeout=60*30):
            msg = await get_live_msg()
            await qq_yk.send_group_msg(group_id=QQ_GROUP_ID, message=msg)

    elif cmd == "PREPARING":
        key = "LT_LY_LIVE_NOTICE_PREPARING"
        if await redis_cache.set_if_not_exists(key=key, value="123", timeout=60*30):
            await qq_yk.send_group_msg(group_id=QQ_GROUP_ID, message="呜呜呜……土豆下播惹（￣へ￣）")


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
