import time
import asyncio
import traceback
from utils.ws import RCWebSocketClient
from utils.dao import SuperDxjUserAccounts, SuperDxjUserSettings, redis_cache
from utils.biliapi import BiliApi, WsApi, CookieFetcher
from config.log4 import super_dxj_logger as logging


class DanmakuProcessor:
    def __init__(self, q, room_id):
        self.q = q
        self.room_id = room_id
        self._settings_load_time = 0
        self._cached_settings = None

        self._is_live = False
        self._last_live_time = 0

        self.gift_list = []
        self.carousel_msg_counter = 100
        self.carousel_msg_index = 0
        self.dmk_q = asyncio.Queue()

        self.cookie = ""
        self.msg_speed_counter = 0
        self.msg_speed_counter_start_time = 0
        self.msg_block_until = 0

        self.cookie_cache_key = f"LT_SUPER_DXJ_USER_COOKIE_{self.room_id}"

    async def load_cookie(self):
        if self.cookie:
            return True, self.cookie

        cookie = await redis_cache.get(self.cookie_cache_key)
        if cookie:
            self.cookie = cookie
            return True, cookie

        config = await self.load_config()
        account = config["account"]
        password = config["password"]
        flag, cookie = await CookieFetcher.get_cookie(account=account, password=password)
        if not flag:
            logging.info(f"Super dxj CookieFetcher.get_cookie Error: {cookie}")
            return False, f"登录失败：{cookie}"

        await redis_cache.set(self.cookie_cache_key, cookie)
        self.cookie = cookie

        logging.info(f"Super dxj CookieFetcher.get_cookie 登录成功！")
        return True, cookie

    async def set_cookie_invalid(self):
        self.cookie = ""
        await redis_cache.delete(self.cookie_cache_key)
        return True

    async def get_live_status(self):
        if self._is_live is False:
            return False

        now = time.time()
        if now - self._last_live_time < 1800:
            return True

        flag, live_status = await BiliApi.get_live_status(room_id=self.room_id)
        if not flag:
            logging.error(f"Cannot get live room status: {live_status}")
            live_status = False

        if live_status:
            self._is_live = True
            self._last_live_time = now
            return True
        else:
            self._is_live = False
            return False

    async def send_danmaku(self):
        while True:
            dmk = await self.dmk_q.get()
            logging.info(f"Need send dmk: {dmk}")

            now = time.time()
            if now < self.msg_block_until:
                continue

            # 计数
            if now - self.msg_speed_counter_start_time > 60:
                self.msg_speed_counter_start_time = now
                self.msg_speed_counter = 0
            self.msg_speed_counter += 1

            # 检查计数
            if self.msg_speed_counter > 60:
                self.msg_block_until = now + 30

            flag, cookie = await self.load_cookie()
            if not flag:
                # 登录失败，冷却1分钟
                self.msg_block_until = now + 60
                continue

            flag, msg = await BiliApi.send_danmaku(message=dmk, room_id=self.room_id, cookie=cookie)
            print(flag, msg)
            if flag:
                continue

            if "412" in msg:
                self.msg_block_until = now + 60 * 5

            elif "账号未登录" in msg:
                await self.set_cookie_invalid()

    async def load_config(self):
        if int(time.time()) - self._settings_load_time < 60 and self._cached_settings:
            return self._cached_settings

        self._cached_settings = await SuperDxjUserSettings.get(room_id=self.room_id)
        self._settings_load_time = time.time()
        return self._cached_settings

    async def proc_one_danmaku(self, dmk):
        settings = await self.load_config()
        cmd = dmk["cmd"]
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
            logging.info(f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}")

            if msg in settings["carousel_msg"]:
                return
            self.carousel_msg_counter = 0

            for key_word, resp in settings["auto_response"]:
                if key_word in msg:
                    self.dmk_q.put_nowait(resp)

        elif cmd == "GUARD_BUY":
            data = dmk.get("data")
            uid = data.get("uid")
            uname = data.get("username", "")
            gift_name = data.get("gift_name", "GUARD")
            price = data.get("price", 0)
            num = data.get("num", 0)
            created_time = data.get("start_time", 0)

            logging.info(f"GUARD_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (price: {price})")
            thank_gold = settings["thank_gold"]
            is_live = await self.get_live_status()
            if (
                thank_gold == 1
                or (thank_gold == 2 and not is_live)
                or (thank_gold == 3 and is_live)
            ):
                thank_gold_text = settings["thank_gold_text"].replace(
                    "{num}", str(num)).replace("{gift}", gift_name).replace("{user}", uname)
                self.dmk_q.put_nowait(thank_gold_text)

        elif cmd == "SEND_GIFT":
            data = dmk.get("data")
            uid = data.get("uid", "--")
            face = data.get("face", "")
            uname = data.get("uname", "")
            gift_name = data.get("giftName", "")
            coin_type = data.get("coin_type", "")
            total_coin = data.get("total_coin", 0)
            num = data.get("num", "")
            is_live = await self.get_live_status()

            if coin_type == "gold":
                thank_gold = settings["thank_gold"]
                if (
                    thank_gold == 1
                    or (thank_gold == 2 and not is_live)
                    or (thank_gold == 3 and is_live)
                ):
                    self.gift_list.append((coin_type, uname, gift_name, num))

            elif coin_type == "silver":
                thank_silver = settings["thank_silver"]
                if (
                    thank_silver == 1
                    or (thank_silver == 2 and not is_live)
                    or (thank_silver == 3 and is_live)
                ):
                    self.gift_list.append((coin_type, uname, gift_name, num))

        elif cmd == "LIVE":
            self._is_live = True
            self._last_live_time = time.time()

        elif cmd == "PREPARING":
            self._is_live = False

        else:
            # print(f"room_id: {self.room_id}: {dmk}")
            pass

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
                        self.dmk_q.put_nowait(message)

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

            self.dmk_q.put_nowait(carousel_msg[self.carousel_msg_index])
            self.carousel_msg_index = (self.carousel_msg_index + 1) % len(carousel_msg)
            self.carousel_msg_counter += 1

    async def run(self):
        flag, live_status = await BiliApi.get_live_status(room_id=self.room_id)
        if not flag:
            logging.error(f"Cannot get live status when init... e: {live_status}")
        else:
            logging.info(f"Live room status: {self.room_id} -> {live_status}")

            self._is_live = bool(live_status)
            self._last_live_time = time.time()

        await asyncio.gather(*[
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

        logging.info(
            f"Ws monitor settings read finished, Need add: {expected}."
        )
        dps = []
        for room_id in expected:
            q = asyncio.Queue()
            await self.new_room(room_id, q)

            dp = DanmakuProcessor(q=q, room_id=room_id)
            dps.append(asyncio.create_task(dp.run()))

        for dp_task in dps:
            await dp_task


async def main():
    logging.info("Super dxj start...")

    mgr = WsManager()
    await mgr.run()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
