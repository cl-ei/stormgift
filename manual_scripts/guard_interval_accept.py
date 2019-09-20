import os
import time
import random
import logging
import asyncio
import requests
from config import LOG_PATH
from utils.dao import redis_cache
from utils.dao import HYMCookies
from utils.biliapi import BiliApi
from config.log4 import console_logger, log_format


log_fh = logging.FileHandler(os.path.join(LOG_PATH, "guard_interval_accept.log"))
log_fh.setFormatter(log_format)
console_logger.addHandler(log_fh)
logging = console_logger


class Core:
    def __init__(self):
        self.cookies = []

    async def load_cookies(self):
        start = time.time()
        r = await HYMCookies.get(return_dict=True)
        self.cookies = []
        for account, data in r.items():
            if not isinstance(data, dict):
                continue
            if "cookie" not in data:
                continue
            if "invalid" in data:
                continue
            if int(time.time()) - data.get("blocked", 0) < 3600*3:
                continue

            self.cookies.append(
                (account, data["cookie"])
            )
        logging.info(f"Got cookies: {len(self.cookies)}/{len(r)}, Cost: {(time.time() - start):.3f}")

    async def get_raffles_and_accept(self):
        url = "https://www.madliar.com/lt/query_gifts?json=true"
        r = requests.get(url).json()
        raffle_list = r['list']
        available = []
        for raffle in raffle_list:
            gift_name = raffle["gift_name"]
            if gift_name not in ("提督", "舰长", "总督"):
                continue

            raffle_id = raffle["raffle_id"]
            key = f"HYM_GUARD_ACCEPT_{raffle_id}"
            if not await redis_cache.set_if_not_exists(key=key, value=1, timeout=3600 * 25):
                continue

            available.append(raffle)
        logging.info(f"Gift list: {len(available)}/{len(raffle_list)}.")

        for raffle in available:
            gift_name = raffle["gift_name"]
            room_id = raffle["real_room_id"]
            raffle_id = raffle["raffle_id"]

            logging.info(f"Now accept: {gift_name} @{room_id} ${raffle_id}...")

            success_count = 0
            try_count = 0
            if gift_name == "舰长":
                chance = 0.1
            else:
                chance = 0.6

            cookie_need_update = False
            for accounts_data in self.cookies:
                if random.random() > chance:
                    continue
                await asyncio.sleep(0.1)

                try_count += 1
                account, cookie = accounts_data
                flag, message = await BiliApi.join_guard(room_id=room_id, gift_id=raffle_id, cookie=cookie, timeout=5)
                if not flag:
                    logging.error(F"Account Failed: {account}, message: {message}")
                    continue

                if "过期" in message:
                    break
                elif "登录" in message:
                    await HYMCookies.set_invalid(account)
                    cookie_need_update = True
                elif "访问被拒绝" in message:
                    await HYMCookies.set_blocked(account)
                    cookie_need_update = True
                else:
                    success_count += 1

            if cookie_need_update:
                await self.load_cookies()

            logging.info(f"Gift: {gift_name} @{room_id} $ {raffle_id} Done. result: {success_count}/{try_count}.")

    async def run(self):
        while True:
            start_time = time.time()
            await self.load_cookies()
            await self.get_raffles_and_accept()

            cost_time = time.time() - start_time
            sleep_time = 60*5 - int(cost_time)
            logging.info(f"Finished! Enter sleep: {sleep_time}.\n")
            await asyncio.sleep(max(0, sleep_time))


app = Core()
loop = asyncio.get_event_loop()
loop.run_until_complete(app.run())
