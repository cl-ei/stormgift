import time
import json
import asyncio
import aiohttp
import requests
import traceback
from utils.dao import redis_cache
from utils.dao import HYMCookies
from config import cloud_acceptor_url
from config.log4 import console_logger as logging


async def join_guard(room_id, gift_id, accounts_data):
    inner_cookies = [_[1] for _ in accounts_data]
    req_json = {
        "act": "join_guard",
        "room_id": room_id,
        "gift_id": gift_id,
        "cookies": inner_cookies,
        "gift_type": "",
    }
    timeout = aiohttp.ClientTimeout(total=50)
    client_session = aiohttp.ClientSession(timeout=timeout)
    try:
        async with client_session as session:
            async with session.post(cloud_acceptor_url, json=req_json) as resp:
                status_code = resp.status
                content = await resp.text()
    except Exception as e:
        logging.error(f"Cannot access cloud acceptor! e: {e}\n{traceback.format_exc()}")
        return

    if status_code != 200:
        return logging.error(f"Accept Failed! e: {content}")

    result_list = json.loads(content)
    success_count = 0
    for index in range(len(result_list)):
        flag, message = result_list[index]
        account, cookie = accounts_data[index]
        if not flag:
            logging.error(f"Cannot accept guard: {flag}, account: {account}, message: {message}")
        else:
            success_count += 1

    logging.info(f"Accept success! @{room_id} ${gift_id}. count: {success_count}.")


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

        tasks = []
        for raffle in r["list"]:
            if raffle["gift_name"] not in ("提督", "舰长", "总督"):
                continue

            raffle_id = raffle["raffle_id"]
            key = f"HYM_GUARD_ACCEPT_{raffle_id}"
            if not await redis_cache.set_if_not_exists(key=key, value=1, timeout=3600*25):
                continue

            offset = 0
            page_count = 100
            while True:
                accounts_data = self.cookies[offset: offset + page_count]
                if not accounts_data:
                    break

                t = join_guard(room_id=raffle["real_room_id"], gift_id=raffle_id, accounts_data=accounts_data)
                tasks.append(loop.create_task(t))

                offset += page_count

        for t in tasks:
            await t
        logging.info("Finished!")

    async def run(self):
        await self.load_cookies()
        await self.get_raffles_and_accept()


app = Core()
loop = asyncio.get_event_loop()
loop.run_until_complete(app.run())
