import time
import logging
import asyncio
from random import choice
from utils.biliapi import WsApi, BiliApi
from utils.ws import RCWebSocketClient
from utils.highlevel_api import DBCookieOperator
from config.log4 import dxj_hansy_logger as logging


class DanmakuSetting(object):
    MONITOR_ROOM_ID = 2937980
    MONITOR_UID = 7411910

    THANK_GIFT = True
    THANK_FOLLOWER = False


class TempData:
    __cached_user_info = {}
    gift_list_for_thank = []

    fans_id_set = None
    cache_count_limit = 10000

    @classmethod
    async def update_user_info(cls, uid, uname, face):
        cls.__cached_user_info[uid] = (uname, face, int(time.time()))
        if len(cls.__cached_user_info) >= cls.cache_count_limit:
            new_dict = {}
            for uname, info_tuple in cls.__cached_user_info.items():
                if time.time() - info_tuple[2] < 3600 * 24 * 7:
                    new_dict[uname] = info_tuple

            logging.info(
                f"TempData.__cached_user_info GC finished, "
                f"old count {len(cls.__cached_user_info)}, new: {len(new_dict)}."
            )
            cls.__cached_user_info = new_dict


async def get_cookie(user="DD"):
    user_cookie_obj = await DBCookieOperator.get_by_uid(user)
    return user_cookie_obj.cookie if user_cookie_obj else ""


async def send_danmaku(msg, user="DD"):
    cookie = await get_cookie(user)

    if not cookie:
        logging.error(f"Cannot get cookie for user: {user}.")
        return

    # MEDAL_ID_OF_77 = 138667
    # MEDAL_ID_OF_HANSY = 10482
    flag, r = await BiliApi.wear_medal(cookie, medal_id=138667)
    if not flag:
        logging.error(f"Cannot wear medal of 77: r: {r}")
        return

    flag, err_msg = await BiliApi.send_danmaku(
        message=msg,
        room_id=DanmakuSetting.MONITOR_ROOM_ID,
        cookie=cookie
    )
    if flag:
        logging.info(f"Danmaku [{msg}] sent, msg: {err_msg}, user: {user}.")
    else:
        logging.error(f"Danmaku [{msg}] send failed, msg: {err_msg}, user: {user}.")
    await BiliApi.wear_medal(cookie, medal_id=10482)


async def proc_message(message):
    cmd = message.get("cmd")
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

        if is_admin or uid in (39748080, 20932326):
            if msg == "开启答谢":
                DanmakuSetting.THANK_GIFT = True
                await send_danmaku("◄∶弹幕答谢已开启。房管发送「关闭答谢」即可关闭。")

            elif msg == "关闭答谢":
                DanmakuSetting.THANK_GIFT = False
                await send_danmaku("◄∶弹幕答谢已关闭。房管发送「开启答谢」即可再次打开。")

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

        logging.info(f"SEND_GIFT: [{coin_type.upper()}] [{uid}] [{uname}] -> {gift_name}*{num} (total_coin: {total_coin})")

        await TempData.update_user_info(uid, uname, face)

    elif cmd == "GUARD_BUY":
        data = message.get("data")

        uid = data.get("uid")
        uname = data.get("username", "")
        gift_name = data.get("gift_name", "GUARD")
        price = data.get("price", 0)
        num = data.get("num", 0)
        created_time = data.get("start_time", 0)
        logging.info(f"GUARD_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (price: {price})")

    elif cmd == "LIVE":
        DanmakuSetting.THANK_FOLLOWER = True

    elif cmd == "PREPARING":
        DanmakuSetting.THANK_FOLLOWER = False


async def thank_gift():
    if not DanmakuSetting.THANK_GIFT:
        return

    thank_list = {}
    need_del = []
    # [uname, gift_name, count, coin_type, created_timestamp]
    for e in TempData.gift_list_for_thank:
        uname, gift_name, count, coin_type, created_timestamp = e
        time_interval = time.time() - created_timestamp
        need_del.append(e)

        if time_interval < 20:
            key = f"{uname}${gift_name}"
            if key in thank_list:
                thank_list[key] += int(count)
            else:
                thank_list[key] = int(count)

    for e in need_del:
        TempData.gift_list_for_thank.remove(e)

    for key, count in thank_list.items():
        uname, gift_name = key.split("$")
        await send_danmaku(f"感谢{uname}赠送的{count}个{gift_name}! 大气大气~")
        logging.info(f"DEBUG: gift_list_for_thank length: {len(TempData.gift_list_for_thank)}, del: {len(need_del)}")


async def get_fans_list():
    result = await BiliApi.get_fans_list(DanmakuSetting.MONITOR_UID)
    return result[::-1]


async def thank_follower():
    if not DanmakuSetting.THANK_FOLLOWER:
        return

    if not isinstance(TempData.fans_id_set, set):
        fl = await get_fans_list()
        if fl:
            TempData.fans_id_set = {x["mid"] for x in fl}
        return

    new_fans_list = await get_fans_list()
    if not new_fans_list:
        return

    new_fans_uid_set = {_["mid"] for _ in new_fans_list}
    thank_uid_list = list(new_fans_uid_set - TempData.fans_id_set)
    if len(thank_uid_list) <= 5:
        while thank_uid_list:
            thank_uid = thank_uid_list.pop(0)
            try:
                uname = [_["uname"] for _ in new_fans_list if _["mid"] == thank_uid][0]
            except Exception as e:
                logging.error(f"Cannot get uname in thank_follower: {e}, thank_uid: {thank_uid}.", exc_info=True)
            else:
                await asyncio.sleep(0.3)
                await send_danmaku(choice([
                    f"谢谢{uname}的关注~相遇是缘，愿常相伴╭❤",
                    f"感谢{uname}的关注~♪（＾∀＾●）",
                    f"感谢{uname}的关注，爱了就别走好吗ノ♥",
                    f"谢谢{uname}的关注，mua~(˙ε˙)",
                ]), user="DD")

    if len(TempData.fans_id_set) < 5000:
        TempData.fans_id_set |= new_fans_uid_set
    else:
        TempData.fans_list = new_fans_uid_set


async def main():
    async def on_connect(ws):
        logging.info("connected.")
        await ws.send(WsApi.gen_join_room_pkg(DanmakuSetting.MONITOR_ROOM_ID))

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
    logging.info("Suki77 ws stated.")

    while True:
        await asyncio.sleep(18)
        await thank_gift()
        await thank_follower()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
