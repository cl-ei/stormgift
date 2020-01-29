import time
import asyncio
from utils.ws import RCWebSocketClient
from utils.dao import SuperDxjUserAccounts, SuperDxjUserSettings, SuperDxjCookieMgr
from utils.biliapi import BiliApi, WsApi
from config.log4 import super_dxj_logger as logging


class DanmakuProcessor:
    def __init__(self, q, room_id, short_room_id=None, name="??"):
        self.q = q
        self.room_id = room_id
        self.short_room_id = short_room_id or room_id
        self.name = name

        self._cached_settings = None
        self._settings_expire_time = 0

        self.is_live = False

        self.gift_list = []
        self.carousel_msg_counter = 100
        self.carousel_msg_index = 0
        self._dmk_q = asyncio.Queue()

        self.cookie = ""

        self.master_uid = None
        self.followers = []

    async def load_cookie(self):
        if self.cookie:
            return True, self.cookie

        config = await self.load_config()
        account = config["account"]
        password = config["password"]
        cookie = await SuperDxjCookieMgr.load_cookie(account=account)
        if cookie:
            self.cookie = cookie
            return True, cookie

        flag, result = await BiliApi.login(account=account, password=password)
        if not flag:
            logging.error(f"Super dxj login Error: {result}")
            return False, f"登录失败：{cookie}"

        cookie = ""
        for k, v in result.items():
            if k not in ("access_token", "refresh_token"):
                cookie += f"{k}={v};"

        await SuperDxjCookieMgr.save_cookie(account=account, cookie=cookie)
        self.cookie = cookie
        logging.info(f"Super dxj 登录成功！{self.room_id}.")
        return True, cookie

    async def set_cookie_invalid(self):
        self.cookie = ""
        config = await self.load_config()
        account = config["account"]
        await SuperDxjCookieMgr.set_invalid(account=account)
        return True

    async def send_danmaku(self):
        msg_block_until = 0

        while True:
            dmk = await self._dmk_q.get()

            now = time.time()
            if now < msg_block_until:
                logging.warning(f"DMK BLOCK: {self.short_room_id}-{self.name} -> {dmk}")
                continue

            flag, cookie = await self.load_cookie()
            if not flag:
                # 登录失败，冷却30秒
                msg_block_until = now + 30
                logging.warning(f"DMK BLOCK(Login failed): {self.short_room_id}-{self.name} -> {dmk}")
                continue

            flag, msg = await BiliApi.send_danmaku(message=dmk, room_id=self.room_id, cookie=cookie)
            if not flag:
                logging.error(f"DMK send failed. {self.short_room_id}-{self.name} -> {dmk}\n\t{msg}")
                if "412" in msg:
                    msg_block_until = now + 60 * 5
                elif "账号未登录" in msg:
                    await self.set_cookie_invalid()

            await asyncio.sleep(1)

    def sch_danmaku(self, dmk):
        if self._dmk_q.qsize() > 15:
            logging.error(f"sch_danmaku abandon: {self.short_room_id}-{self.name} -> {dmk}")
            return
        self._dmk_q.put_nowait(dmk)

    async def load_config(self):
        if self._cached_settings and self._settings_expire_time > time.time():
            return self._cached_settings

        self._cached_settings = await SuperDxjUserSettings.get(room_id=self.room_id)
        self._settings_expire_time = time.time() + 60
        return self._cached_settings

    async def proc_one_danmaku(self, dmk):
        settings = await self.load_config()
        cmd = dmk.get("cmd", "") or ""
        if cmd.startswith("DANMU_MSG"):
            info = dmk.get("info", {})
            msg = str(info[1])
            uid = info[2][0]
            user_name = info[2][1]
            is_admin = info[2][2]
            ul = info[4][0]
            d = info[3]
            dl = d[0] if d else "-"
            deco = d[1] if d else "undefined"
            # logging.info(
            #     f"{self.short_room_id}-{self.name}"
            #     f"\n\t{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}"
            # )

            if msg in settings["carousel_msg"]:
                return
            self.carousel_msg_counter = 0

            for key_word, resp in settings["auto_response"]:
                if key_word in msg:
                    self.sch_danmaku(resp)

        elif cmd == "GUARD_BUY":
            data = dmk.get("data")
            uid = data.get("uid")
            uname = data.get("username", "")
            gift_name = data.get("gift_name", "GUARD")
            price = data.get("price", 0)
            num = data.get("num", 0)
            created_time = data.get("start_time", 0)

            # logging.info(
            #     f"{self.short_room_id}-{self.name} GUARD_GIFT: "
            #     f"[{uid}] [{uname}] -> {gift_name}*{num} (price: {price})"
            # )

            thank_gold = settings["thank_gold"]
            if (
                thank_gold == 1
                or (thank_gold == 2 and not self.is_live)
                or (thank_gold == 3 and self.is_live)
            ):
                thank_gold_text = settings["thank_gold_text"].replace(
                    "{num}", str(num)).replace("{gift}", gift_name).replace("{user}", uname)
                self.sch_danmaku(thank_gold_text)

        elif cmd == "SEND_GIFT":
            data = dmk.get("data")
            uid = data.get("uid", "--")
            face = data.get("face", "")
            uname = data.get("uname", "")
            gift_name = data.get("giftName", "")
            coin_type = data.get("coin_type", "")
            total_coin = data.get("total_coin", 0)
            num = data.get("num", "")

            # logging.info(
            #     f"{self.short_room_id}-{self.name} SEND_GIFT: "
            #     f"[{uid}] [{uname}] -> {gift_name}*{num} (total_coin: {total_coin})"
            # )

            if coin_type == "gold":
                thank_gold = settings["thank_gold"]
                if (
                    thank_gold == 1
                    or (thank_gold == 2 and not self.is_live)
                    or (thank_gold == 3 and self.is_live)
                ):
                    self.gift_list.append((coin_type, uname, gift_name, num))

            elif coin_type == "silver":
                thank_silver = settings["thank_silver"]
                if (
                    thank_silver == 1
                    or (thank_silver == 2 and not self.is_live)
                    or (thank_silver == 3 and self.is_live)
                ):
                    self.gift_list.append((coin_type, uname, gift_name, num))

        elif cmd == "LIVE":
            logging.info(f"LIVE: {self.short_room_id}-{self.name}")
            self.is_live = True

        elif cmd == "PREPARING":
            logging.info(f"PREPARING: {self.short_room_id}-{self.name}")
            self.is_live = False

    async def thank_gift(self):
        while True:
            await asyncio.sleep(20)

            if not self.gift_list:
                continue

            gift_list = self.gift_list
            self.gift_list = []
            config = await self.load_config()
            gift_dict = {}
            for g in gift_list:
                coin_type, uname, gift_name, num = g
                gift_dict.setdefault(coin_type, {}).setdefault(uname, {}).setdefault(gift_name, 0)
                gift_dict[coin_type][uname][gift_name] += num

            for coin_type, gifts in gift_dict.items():
                if coin_type == "gold":
                    tpl = config["thank_gold_text"]
                else:
                    tpl = config["thank_silver_text"]

                for user_name, gift_map in gifts.items():
                    for gift_name, num in gift_map.items():

                        message = tpl.replace("{user}", user_name).replace(
                            "{gift}", gift_name).replace("{num}", str(num))
                        self.sch_danmaku(message)

    async def parse_danmaku(self):
        while True:
            dmk = await self.q.get()
            try:
                await self.proc_one_danmaku(dmk)
            except Exception as e:
                if dmk == {"code": 0}:
                    continue

                logging.error(f"Error happened in processing one dmk: {dmk}, e: {e}")

    async def send_carousel_msg(self):
        sleep_time = 0
        while True:
            await asyncio.sleep(1)
            sleep_time += 1

            config = await self.load_config()
            carousel_msg_interval = config["carousel_msg_interval"]
            carousel_msg = config["carousel_msg"]

            if sleep_time < carousel_msg_interval:
                continue

            sleep_time = 0
            if not carousel_msg:
                continue

            if self.carousel_msg_counter >= len(carousel_msg):
                # 轮播弹幕没有被覆盖，不再播报
                continue

            if self.carousel_msg_index >= len(carousel_msg):
                # 索引超出了，说明进行了缩减操作，因此重置索引和计数器
                self.carousel_msg_index = 0
                self.carousel_msg_counter = 0

            danmaku = carousel_msg[self.carousel_msg_index]
            self.sch_danmaku(danmaku)
            self.carousel_msg_index = (self.carousel_msg_index + 1) % len(carousel_msg)
            self.carousel_msg_counter += 1

    async def thank_follower(self):

        async def get_fans_list():
            if self.master_uid is None:
                self.master_uid = await BiliApi.get_uid_by_live_room_id(self.room_id)
            data = await BiliApi.get_fans_list(self.master_uid)
            return data[::-1]

        while True:
            await asyncio.sleep(20)

            config = await self.load_config()
            if not self.is_live or config["thank_follower"] != 1:
                self.followers = None
                continue

            if not self.followers:
                fans = await get_fans_list()
                self.followers = [x["mid"] for x in fans]
                continue

            new_fans_list = await get_fans_list()
            if not new_fans_list:
                continue

            new_fans_id_list = [x["mid"] for x in new_fans_list]
            thank_uid_list = list(set(new_fans_id_list) - set(self.followers))
            uid_to_name_map = {x["mid"]: x["uname"] for x in new_fans_list}
            thank_follower_text = config["thank_follower_text"]
            for uid in thank_uid_list:
                name = uid_to_name_map.get(uid)
                dmk = thank_follower_text.replace("{user}", name)
                self.sch_danmaku(dmk)

            self.followers.extend(new_fans_id_list)
            self.followers = list(set(self.followers))
            if len(self.followers) > 2000:
                self.followers = list(set(new_fans_id_list))

    async def run(self):
        await asyncio.gather(*[
            self.thank_follower(),
            self.parse_danmaku(),
            self.send_danmaku(),
            self.send_carousel_msg(),
            self.thank_gift(),
        ])


class WsManager(object):
    def __init__(self):
        self._clients = {}
        self.monitor_live_rooms = {}

        self.msg_count = 0
        self._broken_live_rooms = []
        self.heartbeat_pkg = WsApi.gen_heart_beat_pkg()

    async def new_room(self, room_id, q):
        client = self._clients.get(room_id)

        if client and not client.set_shutdown:
            return

        async def on_message(message):
            for msg in WsApi.parse_msg(message):
                self.msg_count += 1
                q.put_nowait(msg)

        async def on_connect(ws):
            await ws.send(WsApi.gen_join_room_pkg(room_id))

            flag, live_status = await BiliApi.get_live_status(room_id=room_id)
            if flag:
                q.put_nowait({"cmd": "LIVE" if live_status else "PREPARING"})

        async def on_error(e, msg):
            self._broken_live_rooms.append(room_id)
            logging.error(f"WS ERROR! room_id: [{room_id}], msg: {msg}, e: {e}")

        new_client = RCWebSocketClient(
            url=WsApi.BILI_WS_URI,
            on_message=on_message,
            on_error=on_error,
            on_connect=on_connect,
            heart_beat_pkg=self.heartbeat_pkg,
            heart_beat_interval=10
        )
        new_client.room_id = room_id
        self._clients[room_id] = new_client
        await new_client.start()

    async def kill_client_and_remove_it(self, room_id):
        client = self._clients.get(room_id)

        if client and not client.set_shutdown:
            await client.kill()
            del self._clients[room_id]

    async def run(self):
        expected = await SuperDxjUserAccounts.get_all_live_rooms()
        expected = [room_id for room_id in expected if room_id != 123]
        if not expected:
            logging.error(f"Cannot load monitor live rooms from redis!")
            return

        self.monitor_live_rooms = expected
        dps = []

        for room_id in expected:
            flag, data = await BiliApi.get_live_room_info_by_room_id(room_id=room_id)
            if flag:
                uid = data["uid"]
                user_name = await BiliApi.get_user_name(uid=uid)
                short_room_id = data["short_id"]
                room_id = data["room_id"]
            else:
                user_name = "??"
                short_room_id = room_id

            q = asyncio.Queue()
            await self.new_room(room_id, q)

            dp = DanmakuProcessor(q=q, room_id=room_id, short_room_id=short_room_id, name=user_name)
            dps.append(asyncio.create_task(dp.run()))

        logging.info(f"Ws monitor settings read finished, Need add: {expected}.")
        for dp_task in dps:
            await dp_task


async def main():
    logging.info("Super dxj start...")

    mgr = WsManager()
    await mgr.run()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
