import re
import logging
import asyncio
import aiohttp
import datetime
from utils.cq import async_zy
from utils.dao import redis_cache
from utils.ws import RCWebSocketClient
from utils.biliapi import WsApi, DmkSender
from config.log4 import dxj_dd_logger as logging


MONITOR_ROOM_ID = 13369254


danmaku_sender = DmkSender(room_id=MONITOR_ROOM_ID, user_id="TZ")


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
    room_id = 13369254
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
    room_id = 13369254
    key = F"LT_SIGN_V2_{room_id}"
    info = await redis_cache.get(key)
    info = info or []
    for s in info:
        if s["id"] == user_id:
            return s["score"]
    return 0


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

        if msg in ("总督", "提督", "舰长", "低保"):
            await danmaku_sender.send("|･ω･｀) 查看下方的主播简介哦")

        elif msg.startswith("#点歌") or msg.startswith("点歌") or msg.startswith("＃点歌"):
            song_name = msg.split("点歌", 1)[-1].strip()
            url = f"http://192.168.100.100:4096/command/{user_name}${song_name}"
            async with aiohttp.request("get", url=url) as _:
                pass

        elif msg in ("签到", "打卡"):
            (
                sign_success, continue_days, total_days,
                rank, current_score, today_sign_count
            ) = await sign_dd(user_id=uid)

            if sign_success:
                prompt = f"今日第{today_sign_count + 1}位{msg}！"
            else:
                prompt = f"已{msg}，"
            message = f"{user_name}{prompt}连续{msg}{continue_days}天、累计{total_days}天，排名第{rank}."
            await danmaku_sender.send(msg=message)

        elif msg == "积分":
            score = await get_score(user_id=uid)
            if score > 9999:
                message = f"{user_name}现在拥有{score/100.0:.2f}积元（1积元=100积分）."
            else:
                message = f"{user_name}现在拥有{score:.2f}积分."
            await danmaku_sender.send(msg=message)

        else:
            for key_word in ("大气大气~", "现在拥有", "连续打卡", "连续签到", "."):
                if key_word in msg:
                    return
            if re.match(r"\S*第?\d\.$", msg):
                return

            await async_zy.send_private_msg(user_id=80873436, message=f"自己的直播间: \n\n{msg_record}")


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
