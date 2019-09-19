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
            if not isinstance(data, dict) or "cookie" not in data:
                continue

            self.cookies.append(
                (account, data["cookie"])
            )
        logging.info(f"Got cookies: {len(r)}, Cost: {(time.time() - start):.3f}")

    async def get_raffles_and_accept(self):
        url = "https://www.madliar.com/lt/query_gifts?json=true"
        r = requests.get(url).json()
        logging.info(f"Gift list: {len(r['list'])}.")
        for raffle in r["list"]:
            gift_name = raffle["gift_name"]
            if gift_name not in ("提督", "舰长", "总督"):
                continue
            room_id = raffle["real_room_id"]
            raffle_id = raffle["raffle_id"]
            key = f"HYM_GUARD_ACCEPT_{raffle_id}"
            if not await redis_cache.set_if_not_exists(key=key, value=1, timeout=3600*25):
                continue

            logging.info(f"Now accept: {gift_name} @{room_id} ${raffle_id}...")

            success_count = 0
            try_count = 0
            chance = 0.05 if gift_name == "舰长" else 0.6
            for accounts_data in self.cookies:
                if random.random() > chance:
                    continue
                await asyncio.sleep(0.3)
                try_count += 1
                account, cookie = accounts_data
                flag, message = await BiliApi.join_guard(room_id=room_id, gift_id=raffle_id, cookie=cookie, timeout=5)
                if flag:
                    success_count += 1
                    # logging.info(f"SUCCESS: account: {account}-{success_count}, message: {message}.")
                else:
                    logging.error(F"Account Failed: {account}, message: {message}")
                if "过期" in message:
                    break
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
