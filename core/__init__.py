import os
import sys
import time
import asyncio
import logging

from utils.ws import ReConnectingWsClient
from utils.biliapi import WsApi, BiliApi


LOG_PATH = "./log"
log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
file_handler = logging.FileHandler(os.path.join(LOG_PATH, "admin_assist.log"), encoding="utf-8")
file_handler.setFormatter(log_format)

logger = logging.getLogger("admin_assist")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)
logger.addHandler(file_handler)
logging = logger


logging.info("正在连接...")


class TempData:
    MONITOR_UID = 0

    silver_gift_list = []
    fans_id_set = set()

    @classmethod
    async def update_fans_id_set(cls):
        return_data = []
        fans_list = await BiliApi.get_fans_list(cls.MONITOR_UID)
        fans_list = fans_list[::-1]

        new_fans_uid_set = {_["mid"] for _ in fans_list}
        thank_uid_list = list(new_fans_uid_set - cls.fans_id_set)

        while thank_uid_list:
            thank_uid = thank_uid_list.pop(0)
            try:
                uname = [_["uname"] for _ in fans_list if _["mid"] == thank_uid][0]
            except Exception as e:
                logging.error(f"Cannot get uname in thank_follower: {e}, thank_uid: {thank_uid}.", exc_info=True)
            else:
                return_data.append(uname)

        if len(TempData.fans_id_set) < 5000:
            TempData.fans_id_set |= new_fans_uid_set
        else:
            TempData.fans_id_set = new_fans_uid_set

        return return_data[:5]


class DanmakuSetting(object):
    MONITOR_ROOM_ID = 2516117

    SESSDATA = ""
    bili_jct = ""
    COOKIE = ""
    MY_UID = 0

    CAROUSEL_INDEX = 0
    CAROUSEL_INTERVAL = 120
    CAROUSEL_MSG = []

    LAST_ACTIVE_TIME = time.time() - 3600

    THANK_FOLLOWER = True
    THANK_SILVER = False
    THANK_GOLD = False

    THANK_TEXT_SILVER = "感谢{uname}赠送的{count}个{gift_name}! 大气大气~"
    THANK_TEXT_GOLD = "感谢{uname}赠送的{count}个{gift_name}! 大气大气~"
    THANK_TEXT_GUARD = "感谢{uname}开通了{count}个月的{gift_name}! 大气大气~"
    THANK_TEXT_FOLLOWER = "谢谢{uname}的关注，mua~(˙ε˙)"

    __config_key_map = {
        "直播间房间号": "MONITOR_ROOM_ID",
        "SESSDATA": "SESSDATA",
        "bili_jct": "bili_jct",
        "答谢关注": "THANK_FOLLOWER",
        "答谢银瓜子礼物": "THANK_SILVER",
        "答谢金瓜子礼物": "THANK_GOLD",
        "新增轮播弹幕": "CAROUSEL_MSG",
        "轮播间隔": "CAROUSEL_INTERVAL",
        "银瓜子": "THANK_TEXT_SILVER",
        "金瓜子": "THANK_TEXT_GOLD",
        "舰长": "THANK_TEXT_GUARD",
        "关注": "THANK_TEXT_FOLLOWER"
    }

    def __init__(self):
        with open("./配置.txt") as f:
            config = f.readlines()
        config = [_.strip() for _ in config if "=" in _ and not _.startswith("#")]

        def parse_config(config_list, key):
            values = []
            for c in config_list:
                k, v = c.split("=", 1)
                if key == k:
                    values.append(v.strip())
            if "新增" in key:
                return values
            else:
                return values[0] if values else None

        config_dict = {}
        for config_raw_key, config_warped_key in self.__config_key_map.items():
            config_dict[config_warped_key] = parse_config(config, config_raw_key)

        for attr_name, attr_value in config_dict.items():
            setattr(self, attr_name, attr_value)

        # load
        self.THANK_FOLLOWER = True if self.THANK_FOLLOWER in (True, "open") else False
        self.THANK_SILVER = True if self.THANK_SILVER in (True, "open") else False
        self.THANK_GOLD = True if self.THANK_GOLD in (True, "open") else False

        self.CAROUSEL_INTERVAL = max(0, int(self.CAROUSEL_INTERVAL))
        self.MONITOR_ROOM_ID = int(self.MONITOR_ROOM_ID)
        self.COOKIE = f"SESSDATA={self.SESSDATA}; bili_jct={self.bili_jct}"

        async def complete_config(self):
            flag, data = await BiliApi.get_user_info(self.COOKIE)
            if not flag:
                logging.error(f"账号配置错误！")
                sys.exit(1)

            self.MY_UID = data.get("uid", 0)
            self.MY_UNAME = data.get("uname", "")

            flag, data = await BiliApi.get_live_room_info(self.MONITOR_ROOM_ID)
            if not flag:
                logging.error(f"直播间号配置错误！")
                sys.exit(1)
            self.MONITOR_ROOM_ID = data.get("room_id", 0)
            short_id = data.get("short_id", 0)

            monitor_uid = await BiliApi.get_uid_by_live_room_id(self.MONITOR_ROOM_ID)
            if monitor_uid <= 0:
                logging.error(f"无法获取主播UID！")
                sys.exit(1)
            TempData.MONITOR_UID = monitor_uid
            r = await TempData.update_fans_id_set()
            if not r:
                logging.error(f"不能读取主播粉丝列表！")
                sys.exit(1)

            logging.info(
                f"\n\n"
                f"\t监控直播间: {self.MONITOR_ROOM_ID}, 短房间号: {short_id}\n"
                f"\t使用账号: {self.MY_UNAME}\n"
                f"\tuid: {self.MY_UID}\n\n"
                f"\t金瓜子答谢: {self.THANK_GOLD}\n"
                f"\t银瓜子答谢: {self.THANK_SILVER}\n"
                f"\t关注答谢: {self.THANK_FOLLOWER}"
            )
            print("_" * 90)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(complete_config(self))

    def get_if_master_is_active(self):
        message_peroid = len(self.CAROUSEL_MSG) * self.CAROUSEL_INTERVAL
        result = time.time() - self.LAST_ACTIVE_TIME < message_peroid
        return result

    def flush_last_active_time(self):
        self.LAST_ACTIVE_TIME = time.time()


class Core(object):
    def __init__(self):
        self.setting = DanmakuSetting()

    async def send_danmaku(self, msg):
        print(f"Send: {msg}")
        return
        await BiliApi.send_danmaku(
            message=msg,
            room_id=self.setting.MONITOR_ROOM_ID,
            cookie=self.setting.COOKIE
        )

    async def proc_message(self, message):
        cmd = message.get("cmd")
        if cmd == "DANMU_MSG":
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

            if msg in self.setting.CAROUSEL_MSG:
                return

            self.setting.flush_last_active_time()
            if is_admin or uid == 20932326:
                if msg == "清空缓存":
                    TempData.fans_id_set = set()
                    await self.send_danmaku("🤖 完成。")

                elif msg == "状态":
                    await self.send_danmaku(
                        f"答谢:"
                        f"金{'开' if self.setting.THANK_GOLD else '关'}-"
                        f"银{'开' if self.setting.THANK_SILVER else '关'}-"
                        f"关注{'开' if self.setting.THANK_FOLLOWER else '关'}-"
                        f"f{len(TempData.fans_id_set)}"
                        f"s{len(TempData.silver_gift_list)}"
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

            if coin_type == "silver":
                logging.info(f"SEND_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (total_coin: {total_coin})")

                if self.setting.THANK_SILVER:
                    TempData.silver_gift_list.append(f"{uname}${gift_name}${num}")

        elif cmd == "COMBO_END":
            data = message.get("data")
            uname = data.get("uname", "")
            gift_name = data.get("gift_name", "")
            price = data.get("price")
            count = data.get("combo_num", 0)
            logging.info(f"GOLD_GIFT: [ ----- ] [{uname}] -> {gift_name}*{count} (total_coin: {price*count})")

            if self.setting.THANK_GOLD:
                await self.thank_gold(uname, count, gift_name)

        elif cmd == "GUARD_BUY":
            data = message.get("data")
            uid = data.get("uid")
            uname = data.get("username", "")
            gift_name = data.get("gift_name", "GUARD")
            price = data.get("price")
            num = data.get("num", 0)
            logging.info(f"GUARD_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (total_coin: {price*num})")

            if self.setting.THANK_GOLD:
                await self.thank_guard(uname, num, gift_name)

        elif cmd == "LIVE":
            pass
        elif cmd == "PREPARING":
            pass

    async def thank_follower(self):
        new_users = await TempData.update_fans_id_set()
        for u in new_users:
            message = self.setting.THANK_TEXT_FOLLOWER.replace("{uname}", u)
            await self.send_danmaku(message)

    async def thank_silver(self):
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
            text = self.setting.THANK_TEXT_SILVER
            message = text.replace("{uname}", uname).replace("{count}", str(num)).replace("{gift_name}", gift_name)
            await self.send_danmaku(message)

    async def thank_gold(self, uname, count, gift_name):
        text = self.setting.THANK_TEXT_GOLD
        message = text.replace("{uname}", uname).replace("{count}", str(count)).replace("{gift_name}", gift_name)
        await self.send_danmaku(message)

    async def thank_guard(self, uname, count, gift_name):
        text = self.setting.THANK_TEXT_GUARD
        message = text.replace("{uname}", uname).replace("{count}", str(count)).replace("{gift_name}", gift_name)
        await self.send_danmaku(message)

    async def send_carousel_msg(self):
        if not self.setting.get_if_master_is_active() or not self.setting.CAROUSEL_MSG:
            return

        msg = self.setting.CAROUSEL_MSG[self.setting.CAROUSEL_INDEX]
        await self.send_danmaku(msg)

        self.setting.CAROUSEL_INDEX = (self.setting.CAROUSEL_INDEX + 1) % len(self.setting.CAROUSEL_MSG)

    async def run(self):
        async def on_connect(ws):
            logging.info("弹幕服务器已连接。")
            await ws.send(WsApi.gen_join_room_pkg(self.setting.MONITOR_ROOM_ID))

        async def on_shut_down():
            logging.error("shutdown!")
            raise RuntimeError("Connection broken!")

        async def on_message(message):
            for m in WsApi.parse_msg(message):
                try:
                    await self.proc_message(m)
                except Exception as e:
                    logging.error(f"Error happened when proc_message: {e}", exc_info=True)

        new_client = ReConnectingWsClient(
            uri=WsApi.BILI_WS_URI,
            on_message=on_message,
            on_connect=on_connect,
            on_shut_down=on_shut_down,
            heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
            heart_beat_interval=10
        )

        await new_client.start()

        counter = -1
        while True:
            await asyncio.sleep(1)
            counter = (counter + 1) % 10000000000

            if counter % 10 == 0 and self.setting.THANK_FOLLOWER:
                await self.thank_follower()
                await self.thank_silver()

            if self.setting.CAROUSEL_INTERVAL > 0 and counter % self.setting.CAROUSEL_INTERVAL == 0:
                await self.send_carousel_msg()
