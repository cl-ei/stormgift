import os
import time
import json
import logging
import asyncio
import datetime
import requests
from config import CQBOT
from cqhttp import CQHttp
from random import choice, random
from utils.biliapi import WsApi, BiliApi
from utils.ws import RCWebSocketClient
from utils.dao import HansyGiftRecords
from utils.highlevel_api import DBCookieOperator
from config.log4 import dxj_hansy_logger as logging


bot = CQHttp(**CQBOT)


class DanmakuSetting(object):
    MONITOR_ROOM_ID = 2516117
    MONITOR_UID = 65568410

    MSG_INTERVAL = 120
    MSG_LIST = [
        "◄∶想要观看直播回放的小伙伴，记得关注录屏组哦~",
        "◄∶喜欢泡泡的小伙伴，加粉丝群436496941来玩耍呀~",
        "◄∶更多好听的原创歌和翻唱作品，网易云音乐搜索「管珩心」~",
        "◄∶你的关注和弹幕是直播的动力，小伙伴们多粗来聊天掰头哇~",
        "◄∶赠送1个B坷垃，就可以领取珩心专属「电磁泡」粉丝勋章啦~",
        "◄∶有能力的伙伴上船支持一下主播鸭~还能获赠纪念礼品OvO",
    ]
    MSG_INDEX = 0

    LAST_ACTIVE_TIME = time.time() - 3600
    THRESHOLD = 79000

    THANK_GIFT = True
    THANK_FOLLOWER = False

    @classmethod
    def get_if_master_is_active(cls):
        message_peroid = len(cls.MSG_LIST) * cls.MSG_INTERVAL
        result = time.time() - cls.LAST_ACTIVE_TIME < message_peroid
        return result

    @classmethod
    def flush_last_active_time(cls):
        cls.LAST_ACTIVE_TIME = time.time()

    # notice
    TEST_GROUP_ID_LIST = [159855203, ]
    NOTICE_GROUP_ID_LIST = [
        159855203,  # test
        883237694,  # guard
        436496941,
        591691708,
    ]
    LAST_LIVE_TIME = time.time() - 3600
    LAST_LIVE_STATUS_UPDATE_TIME = ""


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

    @classmethod
    async def get_user_face_by_uid(cls, uid):
        if uid in cls.__cached_user_info:
            return cls.__cached_user_info[uid][1]
        return None


def send_qq_notice_message(test=False):
    url = "https://api.live.bilibili.com/AppRoom/index?platform=android&room_id=2516117"
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
        image = result.get("data", {}).get("cover")
    except Exception as e:
        logging.exception("Error when get live room info: %s" % e, exc_info=True)
        title = "珩心小姐姐开播啦！快来围观"
        image = "https://i1.hdslb.com/bfs/archive/a6a3d6f3d3582fd5172f6f829c0fe5522705e399.jpg"

    content = "这里是一只易燃易咆哮的小狮子，宝物是糖果锤！嗷呜(っ*´□`)っ~不关注我的通通都要被一！口！吃！掉！"

    groups = DanmakuSetting.TEST_GROUP_ID_LIST if test else DanmakuSetting.NOTICE_GROUP_ID_LIST
    for group_id in groups:
        message = "[CQ:share,url=https://live.bilibili.com/2516117,title=%s,content=%s,image=%s]" % (
            title, content, image
        )
        bot.send(context={"message_type": "group", "group_id": group_id}, message=message)

        message = "[CQ:at,qq=all] \n直播啦！！快来听泡泡唱歌咯，本次直播主题：\n%s" % title
        bot.send(context={"message_type": "group", "group_id": group_id}, message=message)


async def get_cookie(user="LP"):
    user_cookie_obj = await DBCookieOperator.get_by_uid(user)
    return user_cookie_obj.cookie if user_cookie_obj else ""


async def send_hansy_danmaku(msg, user=""):
    if not user:
        user = "LP"
    cookie = await get_cookie(user)

    if not cookie:
        logging.error(f"Cannot get cookie for user: {user}.")
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


async def save_gift(uid, uname, gift_name, coin_type, price, count, created_timestamp, rnd=0, face=None):
    if DanmakuSetting.THANK_GIFT:
        TempData.gift_list_for_thank.append([uname, gift_name, count, coin_type, created_timestamp])

    if coin_type.lower() == "gold":
        await HansyGiftRecords.add_log(uid, uname, gift_name, coin_type, price, count, created_timestamp, rnd)

    if coin_type != "gold" or price*count < DanmakuSetting.THRESHOLD:
        return

    if face is None:
        face = await TempData.get_user_face_by_uid(uid)
    if not face:
        face = await BiliApi.get_user_face(uid)

    data = {
        "created_time": str(datetime.datetime.now()),
        "uid": uid,
        "sender": uname,
        "gift_name": gift_name,
        "count": count,
        "face": face,
    }
    with open("data/hansy_gift_list.txt", "a+") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")
    logging.info(f"New gift saved to `data/hansy_gift_list.txt`, user: {uid}-{uname} -> {gift_name}*{count}.")


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

        if msg.startswith("◄∶"):
            return

        DanmakuSetting.flush_last_active_time()

        if is_admin or uid == 39748080:
            if msg == "开启答谢":
                DanmakuSetting.THANK_GIFT = True
                await send_hansy_danmaku("◄∶弹幕答谢已开启。房管发送「关闭答谢」即可关闭。")

            elif msg == "关闭答谢":
                DanmakuSetting.THANK_GIFT = False
                await send_hansy_danmaku("◄∶弹幕答谢已关闭。房管发送「开启答谢」即可再次打开。")

            elif msg == "开启答谢关注":
                DanmakuSetting.THANK_FOLLOWER = True
                await send_hansy_danmaku("◄∶答谢关注已开启。房管发送「关闭答谢关注」即可关闭。")

            elif msg == "关闭答谢关注":
                DanmakuSetting.THANK_FOLLOWER = False
                TempData.fans_id_set = None
                await send_hansy_danmaku("◄∶答谢关注已关闭。房管发送「开启答谢关注」即可再次打开。")

            elif msg == "清空缓存":
                TempData.fans_id_set = None
                await send_hansy_danmaku("◄∶完成。")

            elif msg == "状态":
                await send_hansy_danmaku(
                    f"礼物{'开' if DanmakuSetting.THANK_GIFT else '关'}-"
                    f"关注{'开' if DanmakuSetting.THANK_FOLLOWER else '关'}"
                )

        if "好听" in msg and random() > 0.7:
            await send_hansy_danmaku(choice([
                "◄∶φ(≧ω≦*)♪好听好听！ 打call ᕕ( ᐛ )ᕗ",
                "◄∶好听！给跪了! ○|￣|_ (这么好听还不摁个关注？！",
                "◄∶好听! 我的大仙泡最美最萌最好听 ´･∀･)乂(･∀･｀",
                "◄∶觉得好听的话，就按个关注别走好吗…(๑˘ ˘๑) ♥",
            ]))

        elif msg[:4] == "#粉丝数":
            query = "".join(msg[4:].split())
            if not query:
                return await send_hansy_danmaku(f"◄∶指令错误。示例： #粉丝数 2516117。")

            if query.isdigit():
                live_room_id = query
                user_id = await BiliApi.get_uid_by_live_room_id(live_room_id)
                if user_id <= 0:
                    return await send_hansy_danmaku(f"◄∶查询失败，错误的直播间号{live_room_id}")
                fans_count = await BiliApi.get_fans_count_by_uid(user_id)
                await send_hansy_danmaku(f"◄∶{live_room_id}直播间有{fans_count}个粉丝。")
            else:
                user_name = query
                flag, user_id = await BiliApi.get_user_id_by_search_way(user_name)
                if not flag or not user_id or user_id <= 0:
                    return await send_hansy_danmaku(f"◄∶查询失败，错误的up主名字{user_name}")
                fans_count = await BiliApi.get_fans_count_by_uid(user_id)
                await send_hansy_danmaku(f"◄∶{user_name}有{fans_count}个粉丝。")

        if uid == 20932326 and msg == "测试通知":
            send_qq_notice_message(test=True)

            time_interval = time.time() - DanmakuSetting.LAST_LIVE_TIME
            message = (
                f"上次开播{time_interval / 60}分钟前，"
                f"刷新时间{DanmakuSetting.LAST_LIVE_STATUS_UPDATE_TIME}."
            )
            bot.send_private_msg(user_id=80873436, message=message)

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

    elif cmd == "LIVE":
        time_interval = time.time() - DanmakuSetting.LAST_LIVE_TIME
        if time_interval > 60 * 40:
            DanmakuSetting.LAST_LIVE_TIME = time.time()
            send_qq_notice_message()

        DanmakuSetting.THANK_GIFT = False
        DanmakuSetting.THANK_FOLLOWER = True
        await send_hansy_danmaku("小仙泡！！！！")

    elif cmd == "PREPARING":
        bot.send_private_msg(user_id=291020256, message="小仙女记得把歌单发我昂~\n [CQ:image,file=1.gif]")

        DanmakuSetting.THANK_GIFT = True
        DanmakuSetting.THANK_FOLLOWER = False
        await send_hansy_danmaku("晚安安啊大坏蛋！")


async def send_carousel_msg():
    if not DanmakuSetting.get_if_master_is_active():
        return

    msg = DanmakuSetting.MSG_LIST[DanmakuSetting.MSG_INDEX]
    await send_hansy_danmaku(msg, user="DD")

    DanmakuSetting.MSG_INDEX = (DanmakuSetting.MSG_INDEX + 1) % len(DanmakuSetting.MSG_LIST)


async def send_recorder_group_danmaku():
    cookie_lp = await get_cookie("LP")
    if cookie_lp:
        await BiliApi.enter_room(DanmakuSetting.MONITOR_ROOM_ID, cookie_lp)


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
        await send_hansy_danmaku(f"感谢{uname}赠送的{count}个{gift_name}! 大气大气~")
        logging.info(f"DEBUG: gift_list_for_thank length: {len(TempData.gift_list_for_thank)}, del: {len(need_del)}")


async def get_fans_list():
    if not DanmakuSetting.MONITOR_UID:
        DanmakuSetting.MONITOR_UID = await BiliApi.get_uid_by_live_room_id(DanmakuSetting.MONITOR_ROOM_ID)
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
                await send_hansy_danmaku(choice([
                    f"谢谢{uname}的关注~相遇是缘，愿常相伴╭❤",
                    f"感谢{uname}的关注~♪（＾∀＾●）",
                    f"感谢{uname}的关注，爱了就别走好吗ノ♥",
                    f"谢谢{uname}的关注，mua~(˙ε˙)",
                ]), user="DD")

    if len(TempData.fans_id_set) < 5000:
        TempData.fans_id_set |= new_fans_uid_set
    else:
        TempData.fans_list = new_fans_uid_set


async def update_hansy_live_status():
    if time.time() - DanmakuSetting.LAST_LIVE_TIME > 60*60:
        return

    flag, r = await BiliApi.get_live_status(room_id=DanmakuSetting.MONITOR_ROOM_ID)
    DanmakuSetting.LAST_LIVE_STATUS_UPDATE_TIME = f"{datetime.datetime.now()}"
    if flag and r:
        DanmakuSetting.LAST_LIVE_TIME = time.time()


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
    logging.info("Hansy ws stated.")

    counter = -1
    while True:
        await asyncio.sleep(1)
        counter = (counter + 1) % 10000000000

        if counter % 15 == 0:
            await thank_gift()
            await thank_follower()

        if counter % DanmakuSetting.MSG_INTERVAL == 0:
            await send_carousel_msg()

        if counter % (60*5) == 0:
            await send_recorder_group_danmaku()

        if counter % (60*6) == 0:
            await update_hansy_live_status()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
