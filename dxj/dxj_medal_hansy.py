import time
import asyncio
import datetime
from config.g import QQ_NUMBER_DD
from utils.cq import async_zy
from utils.dao import redis_cache
from typing import Union, List, Dict
from utils.ws import RCWebSocketClient
from utils.biliapi import WsApi, BiliApi
from config.log4 import dxj_hansy_logger as logging
from utils.reconstruction_model import LTUserCookie
from utils.schema import SendGift


MONITOR_ROOM_ID = 2516117
DANMAKU_SENDER_UID = 87301592

info_queue = asyncio.Queue()


class MedalManager:
    key_prefix = "LT:INTI"
    today_key_prefix = "LT:INTI_TODAY"

    def __init__(self, room_id: int):
        self.room_id = room_id
        self.key = f"{self.key_prefix}:{room_id}"
        self.today_key = f"{self.today_key_prefix}:{room_id}"

    async def set_level_info(self, uid: int, level: int) -> int:
        return await redis_cache.hash_map_set(self.key, {uid: level})

    async def get_level_info(self, *uids: int) -> Dict[int, dict]:
        return await redis_cache.hash_map_get(self.key, *uids)

    async def get_today_prompted(self) -> List[int]:
        return await redis_cache.list_get_all(self.today_key)

    async def add_today_prompted(self, uid: int) -> None:
        await redis_cache.list_push(self.today_key, uid)


mgr = MedalManager(MONITOR_ROOM_ID)


async def notice(user_name: str, medal_name: str, level: int):
    msg = f"恭喜{user_name}的{medal_name}勋章升到{level}级~mua~"
    await send_danmaku(msg, user_id=DANMAKU_SENDER_UID)


async def worker(master_id: int):
    gifts: List[SendGift] = [info_queue.get_nowait() for _ in range(info_queue.qsize())]
    if not gifts:
        return

    user_info: Dict[int, SendGift] = {g.uid: g for g in gifts}
    prompted = await mgr.get_today_prompted()
    update_list = [uid for uid in user_info if uid not in prompted]
    if not update_list:
        return

    update_list, next_time = update_list[:30], update_list[30:]
    if next_time:
        logging.warning(f"Too much! next_time: {len(next_time)} -> {next_time}")
    for uid in next_time:
        gift = user_info[uid]
        info_queue.put_nowait(gift)

    flag, medals = await BiliApi.get_user_medal_list(*update_list)
    if not flag:
        logging.error(f"Cannot get user medal list!")
        return

    user_medal_info = {}
    for uid, data in medals.items():
        uid = int(uid)
        medal = data["medal"].get(str(master_id))
        if medal:
            user_medal_info[uid] = medal

    level_info = await mgr.get_level_info(*user_medal_info)
    for uid, medal in user_medal_info.items():
        user_name = user_info[uid].uname
        current_level = medal["level"]
        cached_level = level_info.get(uid)

        logging.debug(f"{user_name}(uid: {uid}): cached: {cached_level} -> {current_level}")

        if current_level == cached_level:
            continue

        if current_level >= 20:
            await mgr.add_today_prompted(uid)
            continue

        await mgr.set_level_info(uid, current_level)
        if cached_level is None:
            continue

        await notice(user_name, medal["medal_name"], current_level)
        await mgr.add_today_prompted(uid)


async def send_danmaku(msg, user_id=12298306):
    c = await LTUserCookie.get_by_uid(user_id=user_id)
    if not c:
        logging.error(f"Cannot get cookie for user: WANZI {user_id}.")
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
                    await async_zy.send_private_msg(user_id=QQ_NUMBER_DD, message=f"村长登录已过期.")
                    return

                logging.error(f"Dmk send failed, msg: {send_m}, reason: {data}")
                await asyncio.sleep(1.1)
        else:
            logging.error(f"Cannot send danmaku {send_m}. now return.")
            return

        msg = msg[30:]
        if not msg:
            return

        await asyncio.sleep(1.1)


async def main():
    master_id = await BiliApi.get_uid_by_live_room_id(room_id=MONITOR_ROOM_ID)

    async def on_connect(ws):
        logging.info(f"connected. {MONITOR_ROOM_ID}")
        await ws.send(WsApi.gen_join_room_pkg(MONITOR_ROOM_ID))

    async def on_shut_down():
        logging.error("shutdown!")
        raise RuntimeError("Connection broken!")

    async def on_message(message):

        for m in WsApi.parse_msg(message):
            try:
                if m.get("cmd", "") == "SEND_GIFT":
                    gift = SendGift(**m["data"])
                    info_queue.put_nowait(gift)

                elif m.get("cmd", "").startswith("DANMU_MSG"):
                    info = m.get("info", {})
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

    logging.info("MEDAL DXJ stated.")
    interval = 20
    while True:
        start = time.time()
        await worker(master_id)
        cost = time.time() - start

        wait = interval - cost
        if wait > 0:
            await asyncio.sleep(wait)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
