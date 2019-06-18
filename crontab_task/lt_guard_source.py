import asyncio
import requests
from utils.biliapi import BiliApi
from config.log4 import lt_source_logger as logging
from config import LT_RAFFLE_ID_GETTER_HOST, LT_RAFFLE_ID_GETTER_PORT


class GuardScanner(object):
    def __init__(self):
        self.post_prize_url = f"http://{LT_RAFFLE_ID_GETTER_HOST}:{LT_RAFFLE_ID_GETTER_PORT}"

    def post_prize_info(self, room_id):
        params = {
            "action": "prize_notice",
            "key_type": "G",
            "room_id": room_id
        }
        try:
            r = requests.get(url=self.post_prize_url, params=params, timeout=0.5)
            assert r.status_code == 200
            assert "OK" in r.content.decode("utf-8")
        except Exception as e:
            error_message = F"Prize room post failed. room_id: {room_id}, e: {e}"
            logging.error(error_message, exc_info=True)
            return

        logging.info(f"Guard Prize key post success: {room_id}")

    async def run(self):
        flag, r = await BiliApi.get_guard_room_list()
        if not flag:
            logging.error(f"Cannot find guard room. r: {r}")
            return

        for room_id in r:
            await asyncio.sleep(1)
            self.post_prize_info(room_id)


if __name__ == "__main__":
    s = GuardScanner()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(s.run())

