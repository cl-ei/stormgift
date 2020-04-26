import logging
import asyncio
import datetime
from utils.dao import redis_cache
from utils.ws import RCWebSocketClient
from utils.biliapi import WsApi, BiliApi
from config.log4 import dxj_wanzi_logger as logging
from utils.reconstruction_model import LTUserCookie


MONITOR_ROOM_ID = 24541


async def sign_dd(user_id):
    """
        [{
            id: xxx,
            score: xx,
            sign: [221, 220...]
        }...

        ]

    :param user_id:
    :return:
    """
    room_id = MONITOR_ROOM_ID
    key = F"LT_SIGN_V2_{room_id}"
    base = datetime.date.fromisoformat("2020-01-01")
    now = datetime.datetime.now().date()
    today_num = (now - base).days

    info = await redis_cache.get(key=key)
    info = info or []

    # 检查今日已有几人签到
    today_sign_count = 0
    for s in info:
        if today_num in s["sign"]:
            today_sign_count += 1
    dec_score = 0.001 * int(today_sign_count)

    for s in info:
        if s["id"] == user_id:
            if today_num in s["sign"]:
                sign_success = False
            else:
                s["sign"].insert(0, today_num)
                sign_success = True

            continue_days = 0
            for delta in range(len(s["sign"])):
                if (today_num - delta) in s["sign"]:
                    continue_days += 1
                else:
                    break
            total_days = len(s["sign"])

            if sign_success:
                s["score"] += 50 + min(84, 12 * (continue_days - 1)) - dec_score
            current_score = s["score"]
            break
    else:
        # 新用户
        s = {
            "id": user_id,
            "score": 50 - dec_score,
            "sign": [today_num],
        }
        info.append(s)
        continue_days = 1
        total_days = 1
        current_score = s["score"]
        sign_success = True

    await redis_cache.set(key=key, value=info)
    all_scores = sorted([s["score"] for s in info], reverse=True)
    rank = all_scores.index(current_score)
    return sign_success, continue_days, total_days, rank + 1, current_score, today_sign_count


async def get_score(user_id):
    room_id = MONITOR_ROOM_ID
    key = F"LT_SIGN_V2_{room_id}"
    info = await redis_cache.get(key)
    info = info or []
    for s in info:
        if s["id"] == user_id:
            return s["score"]
    return 0


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
                logging.error(f"Dmk send failed, msg: {send_m}, reason: {data}")
                await asyncio.sleep(1.1)
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
        msg = msg.strip()

        if msg in ("签到", "打卡", "卡打", "咔哒"):
            (
                sign_success, continue_days, total_days,
                rank, current_score, today_sign_count
            ) = await sign_dd(user_id=uid)

            if sign_success:
                prompt = f"今日第{today_sign_count + 1}位{msg}！"
            else:
                prompt = f"已{msg}，"
            message = f"{user_name}{prompt}连续{msg}{continue_days}天、累计{total_days}天，排名第{rank}."
            await send_danmaku(msg=message)

        elif msg == "积分":
            score = await get_score(user_id=uid)
            message = f"{user_name}现在拥有{score:.2f}积分."
            await send_danmaku(msg=message)


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

    logging.info("DD ws stated.")
    while True:
        await asyncio.sleep(1)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
