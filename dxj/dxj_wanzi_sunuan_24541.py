import time
import logging
import asyncio
from typing import List, Dict
from config.g import BILI_UID_WZ
from config.log4 import dxj_wanzi_logger as logging
from utils.schema import SendGift
from utils.ws import RCWebSocketClient
from utils.dao import MedalManager, SignManager
from utils.biliapi import WsApi, BiliApi, DmkSender


MONITOR_ROOM_ID = 24541
medal_iq = asyncio.Queue()
medal_mgr = MedalManager(room_id=MONITOR_ROOM_ID)
dmk_sender = DmkSender(room_id=MONITOR_ROOM_ID, user_id=BILI_UID_WZ)


async def worker(master_id: int):
    gifts: List[SendGift] = [medal_iq.get_nowait() for _ in range(medal_iq.qsize())]
    if not gifts:
        return

    user_info: Dict[int, SendGift] = {g.uid: g for g in gifts}
    prompted = await medal_mgr.get_today_prompted()
    update_list = [uid for uid in user_info if uid not in prompted]
    if not update_list:
        return

    update_list, next_time = update_list[:30], update_list[30:]
    if next_time:
        logging.warning(f"Too much! next_time: {len(next_time)} -> {next_time}")
    for uid in next_time:
        gift = user_info[uid]
        medal_iq.put_nowait(gift)

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

    level_info = await medal_mgr.get_level_info(*user_medal_info)
    for uid, medal in user_medal_info.items():
        user_name = user_info[uid].uname
        current_level = medal["level"]
        cached_level = level_info.get(uid)

        logging.debug(f"{user_name}(uid: {uid}): cached: {cached_level} -> {current_level}")

        if current_level == cached_level:
            continue

        if current_level >= 20:
            await medal_mgr.add_today_prompted(uid)
            continue

        await medal_mgr.set_level_info(uid, current_level)
        if cached_level is None:
            continue

        # do notice!
        medal_name = medal["medal_name"]
        danmaku = f"恭喜{user_name}的【{medal_name}】勋章升级到{current_level}级~~"
        flag, reason = await dmk_sender.send(msg=danmaku)
        if not flag:
            logging.error(f"弹幕发送失败: {reason}")

        await medal_mgr.add_today_prompted(uid)


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
        msg = msg.strip()

        if msg in ("签到", "打卡", "卡打", "咔哒"):
            sign_mgr = SignManager(room_id=MONITOR_ROOM_ID, user_id=uid)
            (
                sign_success, continue_days, total_days,
                rank, current_score, today_sign_count
            ) = await sign_mgr.sign_dd()

            if sign_success:
                prompt = f"今日第{today_sign_count + 1}位{msg}！"
            else:
                prompt = f"已{msg}，"
            message = f"{user_name}{prompt}连续{msg}{continue_days}天、累计{total_days}天，排名第{rank}."
            flag, reason = await dmk_sender.send(msg=message)
            if not flag:
                logging.error(f"弹幕发送失败: {reason}")

        elif msg == "积分":
            sign_mgr = SignManager(room_id=MONITOR_ROOM_ID, user_id=uid)
            score = await sign_mgr.get_score()
            message = f"{user_name}现在拥有{score:.2f}积分."
            flag, reason = await dmk_sender.send(msg=message)
            if not flag:
                logging.error(f"弹幕发送失败: {reason}")

    elif cmd == "SEND_GIFT":
        gift = SendGift(**message["data"])
        medal_iq.put_nowait(gift)


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

    master_id = await BiliApi.get_uid_by_live_room_id(room_id=MONITOR_ROOM_ID)
    logging.info(f"MEDAL DXJ stated. master_id: {master_id}")
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
