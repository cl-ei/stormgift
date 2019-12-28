import asyncio
import aiohttp
from utils.udp import mq_source_to_raffle
from utils.biliapi import WsApi, BiliApi
from config.log4 import lt_server_logger as logging

prize_room_q = asyncio.Queue()

DANMAKU_WS_URL = "ws://broadcastlv.chat.bilibili.com:2244/sub"
CLIENTS_MAP = {
    # 1: {ws, ws, ws}
    # 2: {ws, ws, ws}
    # ...
}


async def heart_beat():
    heart_beat_package = WsApi.gen_heart_beat_pkg()
    while True:
        await asyncio.sleep(30)
        for clients in CLIENTS_MAP.values():
            for ws in clients:
                if not ws.closed:
                    await ws.send_bytes(heart_beat_package)


async def monitor(index):

    async def proc_danmaku(area_id, room_id, raw_msg):
        for danmaku in WsApi.parse_msg(raw_msg):
            try:
                cmd = danmaku.get("cmd")
                if cmd == "PREPARING":
                    return True

                elif cmd == "NOTICE_MSG":
                    msg_type = danmaku.get("msg_type")
                    if msg_type in (2, 8):
                        real_room_id = danmaku['real_roomid']
                        logging.info(f"\tNOTICE_MSG danmaku: {danmaku}")
                        await mq_source_to_raffle.put(("T", real_room_id))

                elif cmd == "GUARD_MSG" and danmaku["buy_type"] == 1:  # and area_id == 1:
                    prize_room_id = danmaku['roomid']  # TODO: need find real room id.
                    await mq_source_to_raffle.put(("G", prize_room_id))

            except KeyError:
                continue

    async def listen_ws(area_id, room_id):
        is_preparing = False
        session = aiohttp.ClientSession()
        async with session.ws_connect(url=DANMAKU_WS_URL) as ws:
            await ws.send_bytes(WsApi.gen_join_room_pkg(room_id=room_id))

            ws.monitor_room_id = room_id
            CLIENTS_MAP.setdefault(area_id, set()).add(ws)

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.ERROR:
                    break

                is_preparing = await proc_danmaku(area_id, room_id, msg.data)
                if is_preparing is True:
                    break

        CLIENTS_MAP[area_id].remove(ws)
        logging.info(f"Client closed. {area_id} -> {room_id}, By danmaku preparing: {is_preparing}")

    async def get_living_room_id(area_id, old_room_id):
        while True:
            flag, result = await BiliApi.get_living_rooms_by_area(area_id=area_id)
            if flag:
                existed_rooms = [ws.monitor_room_id for ws in CLIENTS_MAP.get(area_id, [])]
                for room_id in result:
                    if room_id not in existed_rooms and room_id != old_room_id:
                        logging.info(f"Get live rooms from Biliapi, {index}-{area_id} -> {room_id}")
                        return room_id
            else:
                logging.error(f"Cannot get live rooms from Biliapi. {index}-{area_id} -> {result}")

            await asyncio.sleep(30)

    my_area_id = index % 6 + 1
    my_room_id = None
    while True:
        my_room_id = await get_living_room_id(my_area_id, my_room_id)
        await listen_ws(area_id=my_area_id, room_id=my_room_id)


loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.gather(
    heart_beat(),
    *[monitor(i) for i in range(0, 18)]
))
