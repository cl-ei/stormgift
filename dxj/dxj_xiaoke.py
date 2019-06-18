import os
import sys
import asyncio
from utils.ws import ReConnectingWsClient
from utils.biliapi import WsApi, BiliApi
import logging

try:
    proc_num = int(sys.argv[1])
except (IndexError, ValueError):
    proc_num = 0

ROOM_ID_MAP = {
    0: 11472492,
}

from config.log4 import dxj_xiaoke_logger as logging


class DanmakuSetting:
    MONITOR_ROOM_ID = ROOM_ID_MAP[proc_num]
    MONITOR_UID = None

    THANK_BLACK_UID_LIST = set()

    @classmethod
    def load_config(cls, config_name):
        config_file_name = f"dxj_xiaoke-{proc_num}-{cls.MONITOR_ROOM_ID}.{config_name}"
        config_file_path = "/home/wwwroot/stormgift/data" if "linux" in sys.platform else "./data/"
        return os.path.exists(os.path.join(config_file_path, config_file_name))

    @classmethod
    def set_config(cls, config_name, r):
        config_file_name = f"dxj_xiaoke-{proc_num}-{cls.MONITOR_ROOM_ID}.{config_name}"
        config_file_path = "/home/wwwroot/stormgift/data" if "linux" in sys.platform else "./data/"
        config_file = os.path.join(config_file_path, config_file_name)
        if r:
            if not os.path.exists(config_file):
                with open(config_file, "w"):
                    pass
        else:
            if os.path.exists(config_file):
                os.remove(config_file)
        return True

    @classmethod
    def get_if_thank_silver(cls):
        return cls.load_config("thank_silver")

    @classmethod
    def get_if_thank_gold(cls):
        return cls.load_config("thank_gold")

    @classmethod
    def get_if_thank_follower(cls):
        return cls.load_config("thank_follower")

    @classmethod
    def set_thank_silver(cls, r):
        return cls.set_config("thank_silver", r)

    @classmethod
    def set_thank_gold(cls, r):
        return cls.set_config("thank_gold", r)

    @classmethod
    def set_thank_follower(cls, r):
        return cls.set_config("thank_follower", r)


DanmakuSetting.GIFT_THANK_SILVER = DanmakuSetting.load_config("thank_silver")
DanmakuSetting.GIFT_THANK_GOLD = DanmakuSetting.load_config("thank_gold")
DanmakuSetting.FOLLOWER_THANK = DanmakuSetting.load_config("thank_follower")


class TempData:
    uname_to_id_map = {}
    silver_gift_list = []
    fans_list = None


async def get_cookie():
    uid = "20932326;"  # DD
    with open("data/valid_cookies.txt") as f:
        for c in f.readlines():
            if uid in c:
                return c.strip()
    return ""


async def send_danmaku(msg):
    cookie = await get_cookie()
    if not cookie:
        return

    await BiliApi.send_danmaku(
        message=msg,
        room_id=DanmakuSetting.MONITOR_ROOM_ID,
        cookie=cookie
    )


async def get_fans_list():
    if not DanmakuSetting.MONITOR_UID:
        DanmakuSetting.MONITOR_UID = await BiliApi.get_uid_by_live_room_id(DanmakuSetting.MONITOR_ROOM_ID)
    result = await BiliApi.get_fans_list(DanmakuSetting.MONITOR_UID)
    return result[::-1]


async def proc_message(message):
    cmd = message.get("cmd")
    if cmd.startswith("DANMU_MSG"):
        info = message.get("info", {})
        msg = info[1]
        uid = info[2][0]
        user_name = info[2][1]
        is_admin = info[2][2]
        ul = info[4][0]
        d = info[3]
        dl = d[0] if d else "0"
        deco = d[1] if d else "^^"
        logging.info(f"{'[管]' if is_admin else ''}[{uid}] [{user_name}][{ul}] [{deco} {dl}]-> {msg}")

        if uid in [DanmakuSetting.MONITOR_UID, 12298306, 20932326]:
            if msg == "关闭答谢":
                DanmakuSetting.GIFT_THANK_SILVER = False
                DanmakuSetting.set_thank_silver(False)

                DanmakuSetting.GIFT_THANK_GOLD = False
                DanmakuSetting.set_thank_gold(False)

                await send_danmaku("礼物答谢已关闭。房管发送「开启答谢」可以再次打开。")

            elif msg == "开启答谢":
                DanmakuSetting.GIFT_THANK_GOLD = True
                DanmakuSetting.set_thank_gold(True)
                await send_danmaku("金瓜子礼物答谢已开启。房管发送「关闭答谢」即可关闭。")

            if msg == "关闭答谢辣条":
                DanmakuSetting.GIFT_THANK_SILVER = False
                DanmakuSetting.set_thank_silver(False)
                await send_danmaku("辣条答谢已关闭。房管发送「开启答谢辣条」可以再次打开。")

            elif msg == "开启答谢辣条":
                DanmakuSetting.GIFT_THANK_SILVER = True
                DanmakuSetting.set_thank_silver(True)
                await send_danmaku("辣条答谢已开启。房管发送「关闭答谢辣条」即可关闭。")

            if msg == "关闭答谢关注":
                DanmakuSetting.FOLLOWER_THANK = False
                DanmakuSetting.set_thank_follower(False)

                TempData.fans_list = None
                await send_danmaku("答谢关注者功能已关闭。房管发送「开启答谢关注」可以再次打开。")

            elif msg == "开启答谢关注":
                DanmakuSetting.FOLLOWER_THANK = True
                DanmakuSetting.set_thank_follower(True)
                await send_danmaku("答谢关注者功能已开启。房管发送「关闭答谢关注」即可关闭。")

            elif msg == "答谢姬设置" or msg == "状态":
                fans_list_len = len(TempData.fans_list) if TempData.fans_list else "X"
                cache_count = f"{fans_list_len}-{len(TempData.silver_gift_list)}-{len(TempData.uname_to_id_map)}"
                await send_danmaku(
                    f"答谢:金瓜子{'开启' if DanmakuSetting.GIFT_THANK_GOLD else '关闭'}-"
                    f"辣条{'开启' if DanmakuSetting.GIFT_THANK_SILVER else '关闭'}-"
                    f"关注{'开启' if DanmakuSetting.FOLLOWER_THANK else '关闭'}-{cache_count}"
                )

            elif msg == "指令":
                await send_danmaku(
                    f"{'关闭' if DanmakuSetting.GIFT_THANK_SILVER else '开启'}答谢辣条、"
                    f"{'关闭答谢' if DanmakuSetting.GIFT_THANK_GOLD else '开启答谢（仅开启答谢金瓜子）'}、"
                    f"{'关闭' if DanmakuSetting.FOLLOWER_THANK else '开启'}答谢关注"
                )

    elif cmd == "SEND_GIFT":
        data = message.get("data")
        uid = data.get("uid", "--")
        face = data.get("face", "")
        uname = data.get("uname", "")
        gift_name = data.get("giftName", "")
        coin_type = data.get("coin_type", "")
        total_coin = data.get("total_coin", 0)
        num = data.get("num", "")
        if coin_type != "gold" and DanmakuSetting.GIFT_THANK_SILVER and uid not in DanmakuSetting.THANK_BLACK_UID_LIST:
            TempData.silver_gift_list.append(f"{uname}${gift_name}${num}")
        else:
            if len(TempData.uname_to_id_map) < 10000:
                TempData.uname_to_id_map[uname] = uid
            else:
                TempData.uname_to_id_map = {uname: uid}

    elif cmd == "COMBO_END":
        data = message.get("data")
        uname = data.get("uname", "")
        gift_name = data.get("gift_name", "")
        price = data.get("price")
        count = data.get("combo_num", 0)
        if DanmakuSetting.GIFT_THANK_GOLD:
            if TempData.uname_to_id_map.get(uname) not in DanmakuSetting.THANK_BLACK_UID_LIST:
                await send_danmaku(f"感谢{uname}赠送的{count}个{gift_name}! 大气大气~")

    elif cmd == "GUARD_BUY":
        data = message.get("data")
        uid = data.get("uid")
        uname = data.get("username", "")
        gift_name = data.get("gift_name", "GUARD")
        price = data.get("price")
        num = data.get("num", 0)
        if DanmakuSetting.GIFT_THANK_GOLD:
            if uid not in DanmakuSetting.THANK_BLACK_UID_LIST:
                await send_danmaku(f"感谢{uname}开通了{num}个月的{gift_name}! 大气大气~")

    elif cmd == "LIVE":
        DanmakuSetting.FOLLOWER_THANK = True
        DanmakuSetting.set_thank_follower(True)

    elif cmd == "PREPARING":
        DanmakuSetting.FOLLOWER_THANK = False
        DanmakuSetting.set_thank_follower(False)
        TempData.fans_list = None


async def thank_gift():
    gift_list = {}
    while TempData.silver_gift_list:
        gift = TempData.silver_gift_list.pop()
        uname, gift_name, num = gift.split("$")
        key = f"{uname}${gift_name}"
        if key in gift_list:
            gift_list[key] += int(num)
        else:
            gift_list[key] = int(num)

    for key, num in gift_list.items():
        uname, gift_name = key.split("$")
        await send_danmaku(f"感谢{uname}赠送的{num}个{gift_name}! 大气大气~")


async def thank_follower():

    # block
    return True

    if TempData.fans_list is None:
        fl = await get_fans_list()
        if fl:
            TempData.fans_list = [x["mid"] for x in fl]
    else:
        new_fans_list = await get_fans_list()
        if new_fans_list:
            new_fans_uid_list = {_["mid"] for _ in new_fans_list}
            thank_uid_list = list(new_fans_uid_list - set(TempData.fans_list))
            if len(thank_uid_list) < 5:
                while thank_uid_list:
                    try:
                        uname = [_["uname"] for _ in new_fans_list if _["mid"] == thank_uid_list[0]][0]
                    except Exception:
                        pass
                    else:
                        await send_danmaku(f"谢谢{uname}的关注~啾咪(•̀ω•́)✧")
                    thank_uid_list.pop(0)
                    await asyncio.sleep(0.4)
            if len(TempData.fans_list) < 2000:
                TempData.fans_list = list(set(TempData.fans_list) | new_fans_uid_list)
            else:
                TempData.fans_list = new_fans_uid_list


async def main():
    if not DanmakuSetting.MONITOR_UID:
        DanmakuSetting.MONITOR_UID = await BiliApi.get_uid_by_live_room_id(DanmakuSetting.MONITOR_ROOM_ID)

    async def on_connect(ws):
        logging.info("On connected...")
        await ws.send(WsApi.gen_join_room_pkg(DanmakuSetting.MONITOR_ROOM_ID))

    async def on_shut_down():
        logging.error("shutdown!")

    async def on_message(message):
        for msg in WsApi.parse_msg(message):
            await proc_message(msg)

    new_client = ReConnectingWsClient(
        uri=WsApi.BILI_WS_URI,
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()
    logging.info("Stated.")

    while True:
        if DanmakuSetting.GIFT_THANK_SILVER:
            try:
                await thank_gift()
            except Exception as e:
                logging.error(f"Error in thank_gift: {e}", exc_info=True)

        if DanmakuSetting.FOLLOWER_THANK:
            try:
                await thank_follower()
            except Exception as e:
                logging.error(f"Error in thank_follower: {e}", exc_info=True)
        await asyncio.sleep(10)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
