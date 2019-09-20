import sys
import pickle
import traceback
import asyncio
import logging
from utils.biliapi import CookieFetcher
from utils.dao import HYMCookiesOfCl as HYMCookies
from config.log4 import console_logger as logging
from utils.biliapi import BiliApi


class H:
    def __init__(self, target):
        self.accounts_file = "./cl_accounts.txt"
        self.accounts = []
        self.cookies = []
        self.target = target

    async def load_accounts(self):
        with open(self.accounts_file, "r") as f:
            content = f.readlines()
        for l in content:
            account, password, *_ = l.strip().split("----")
            self.accounts.append((account, password))

    async def login(self, account, password):
        flag, cookie = await CookieFetcher.get_cookie(account, password)
        if not flag:
            logging.error(f"▆▆IMPORTANT▆▆ Cannot get_cookie for account: {account}! message: {cookie}")
            return

        await HYMCookies.add(account=account, password=password, cookie=cookie)
        logging.info(f"▆▆IMPORTANT▆▆ {account} Success! {account}, pass: {password}")

    async def execute(self, proc_index, account, password):
        try_times = -1
        while try_times < 3:
            cookie = await HYMCookies.get(account=account)
            if isinstance(cookie, dict) and "cookie" in cookie:
                cookie = cookie["cookie"]
            else:
                await self.login(account=account, password=password)
                continue
            try_times += 1

            try:
                r = await self.target(proc_index, cookie)
            except Exception as e:
                logging.error(f"Error in self.target: {e}\n\n{traceback.format_exc()}")
                return

            if not isinstance(r, tuple) or len(r) != 2:
                flag, result = True, {}
            else:
                flag, result = r
            result.setdefault("message", "")

            if flag:
                logging.info(f"Target Success! try: {try_times}, message: {result['message']}")
                return

            logging.error(f"Target Failed! try: {try_times}, message: {result['message']}")
            if result.get("re_login") is True:
                await self.login(account=account, password=password)

    async def run(self):
        await self.load_accounts()

        proc_index = -1
        for account, password in self.accounts:
            proc_index += 1
            logging.info(f"\n┏{'-' * 80}┓")
            await self.execute(proc_index, account, password)
            logging.info(f"end of proc: {proc_index}.\n┗{'-' * 80}┛")


async def hao_yang_mao_exec(proc_index, cookie):
    if cookie is None:
        logging.error(f"Bad cookie! {cookie}")
        return False, {"re_login": True}

    # # do sign.
    # flag, result = await BiliApi.do_sign(cookie)
    # if not flag and "请先登录" in result:
    #     logging.warning(f"Do sign failed. result: {result}")
    #     return False, {"re_login": True}
    # logging.info("Sign success!")

    # 送辣条！
    ruid = 20932326
    live_room_id = 13369254
    bag_list = await BiliApi.get_bag_list(cookie)
    send_msg = "\n".join([f"{s['corner_mark']}辣条 * {s['gift_num']}" for s in bag_list if s["gift_name"] == "辣条"])
    logging.info(f"bag_list: \n{send_msg}\n")

    for gift in bag_list:
        if gift["gift_name"] == "辣条":
            flag, data = await BiliApi.send_gift(
                gift["gift_id"], gift["gift_num"], None, gift["bag_id"], ruid, live_room_id, cookie
            )
            if not flag:
                logging.info(f"♨ Send failed, msg: {data.get('message', 'unknown')}")
            else:
                logging.info(f"♨ Send Success! msg: {data.get('message', 'unknown')}")


if __name__ == "__main__":
    hym = H(target=hao_yang_mao_exec)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(hym.run())
