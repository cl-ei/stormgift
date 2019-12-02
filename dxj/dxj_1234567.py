import logging
import asyncio
from utils.cq import async_zy
from utils.biliapi import WsApi
from utils.ws import RCWebSocketClient
from config.log4 import dxj_dd_logger as logging
from utils.dao import redis_cache, BiliToQQBindInfo


MONITOR_ROOM_ID = 1234567


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

        if msg == "再见":
            qq = await BiliToQQBindInfo.unbind(bili=uid)
            await async_zy.send_private_msg(user_id=qq, message=f"你已成功解绑Bili账号:\n{user_name}({uid}).")

        elif msg.startswith("你好"):
            code = msg[2:]
            if not code:
                return

            key = f"BILI_BIND_CHECK_KEY_{code}"
            qq = await redis_cache.get(key)
            if not qq:
                return

            await BiliToQQBindInfo.bind(qq=qq, bili=uid)
            await async_zy.send_private_msg(
                user_id=qq,
                message=f"你已成功绑定到Bili账号:\n{user_name}({uid}).\n如需解绑，请在此直播间发送以下指令:\n\n再见"
            )


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

    logging.info("DD ws stated.")
    while True:
        await asyncio.sleep(1)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
