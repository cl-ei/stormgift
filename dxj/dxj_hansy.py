import datetime
import json
import logging
import asyncio
import requests
from utils.cq import bot
from utils.biliapi import WsApi
from utils.ws import RCWebSocketClient
from utils.dao import HansyGiftRecords, redis_cache
from config.log4 import dxj_hansy_logger as logging


MONITOR_ROOM_ID = 2516117
NOTICE_GROUP_ID_LIST = [
    883237694,  # guard
    436496941,
    591691708,
]


def send_qq_notice_message(test=False):
    url = "https://api.live.bilibili.com/room/v1/Room/get_info?room_id=2516117"
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/webp,image/apng,*/*;q=0.8"
        ),
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/70.0.3538.110 Safari/537.36"
        ),
    }
    try:
        r = requests.get(url=url, headers=headers)
        if r.status_code != 200:
            raise Exception("Error status code!")
        result = json.loads(r.content.decode("utf-8"))
        title = result.get("data", {}).get("title")
        image = result.get("data", {}).get("keyframe")
    except Exception as e:
        logging.exception("Error when get live room info: %s" % e, exc_info=True)
        title = "珩心小姐姐开播啦！快来围观"
        image = "https://i1.hdslb.com/bfs/archive/a6a3d6f3d3582fd5172f6f829c0fe5522705e399.jpg"

    content = "这里是一只易燃易咆哮的小狮子，宝物是糖果锤！嗷呜(っ*´□`)っ~不关注我的通通都要被一！口！吃！掉！"
    message_1 = f"[CQ:share,url=https://live.bilibili.com/2516117,title={title},content={content},image={image}]"
    message_2 = f"[CQ:at,qq=all] \n直播啦！！快来听泡泡唱歌咯，本次直播主题：\n{title}"
    if test:
        bot.send_private_msg(user_id=80873436, message=message_1)
        bot.send_private_msg(user_id=80873436, message=message_2)
        return

    for group_id in NOTICE_GROUP_ID_LIST:
        bot.send_group_msg(group_id=group_id, message=message_1)
        bot.send_group_msg(group_id=group_id, message=message_2)


async def save_gift(uid, uname, gift_name, coin_type, price, count, created_timestamp, rnd=0, face=None):
    if coin_type.lower() == "gold":
        r = await HansyGiftRecords.add_log(uid, uname, gift_name, coin_type, price, count, created_timestamp, rnd)
        logging.info(f"HansyGiftRecords.add_log: user: {uid}-{uname} -> {gift_name}*{count}. r: {r}")


async def proc_message(message):
    cmd = message.get("cmd", "") or ""
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
        logging.info(f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}")

    elif cmd == "SEND_GIFT":
        data = message.get("data")

        uid = data.get("uid", "--")
        face = data.get("face", "")
        uname = data.get("uname", "")
        gift_name = data.get("giftName", "")
        coin_type = data.get("coin_type", "")
        total_coin = data.get("total_coin", 0)
        num = data.get("num", 0)
        price = total_coin // max(1, num)
        rnd = data.get("rnd", 0)
        created_time = data.get("timestamp", 0)

        logging.info(
            f"SEND_GIFT: [{coin_type.upper()}] [{uid}] [{uname}] -> "
            f"{gift_name}*{num} (total_coin: {total_coin})"
        )
        await save_gift(
            uname=uname,
            gift_name=gift_name,
            coin_type=coin_type,
            price=price,
            count=num,
            created_timestamp=created_time,
            uid=uid,
            rnd=rnd,
            face=face
        )

    elif cmd == "GUARD_BUY":
        data = message.get("data")

        uid = data.get("uid")
        uname = data.get("username", "")
        gift_name = data.get("gift_name", "GUARD")
        price = data.get("price", 0)
        num = data.get("num", 0)
        created_time = data.get("start_time", 0)

        logging.info(f"GUARD_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (price: {price})")
        await save_gift(
            uid=uid,
            uname=uname,
            gift_name=gift_name,
            coin_type="gold" if price > 0 else "silver",
            price=price,
            count=num,
            created_timestamp=created_time,
        )

    # elif cmd == "LIVE":
    #     key = "LT_HANSY_DXJ_QQ_NOTICE_TIME"
    #     last_notice_time = await redis_cache.get(key)
    #
    #     if last_notice_time:
    #         logging.info(f"Hansy lived notice time: {last_notice_time}")
    #
    #     else:
    #         await redis_cache.set(key, f"{datetime.datetime.now()}", timeout=1800)
    #         send_qq_notice_message()

    # elif cmd == "PREPARING":
    #     bot.send_private_msg(user_id=291020256, message="大坏蛋记得把歌单发给我！\n [CQ:image,file=1.gif]")


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
    logging.info("Hansy ws stated.")

    while True:
        await asyncio.sleep(10)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
