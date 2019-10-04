import sys
import pickle
import traceback
import asyncio
import logging
from utils.biliapi import CookieFetcher
from utils.dao import HYMCookiesOfCl as hao_yang_mao_class
from config.log4 import console_logger as logging
from utils.biliapi import BiliApi



async def main():
    accounts_file = "./cl_accounts.txt"

    with open(accounts_file, "r") as f:
        content = f.readlines()

    for l in content:
        account, *_, password = l.strip().split("-")
        r = await hao_yang_mao_class.get(account=account)

        if r:
            logging.info(f"Existed: {account}.")

        else:
            flag, cookie = await CookieFetcher.get_cookie(account, password)
            if not flag:
                logging.error(f"▆▆IMPORTANT▆▆ Cannot get_cookie for account: {account}! message: {cookie}")
                return
            await hao_yang_mao_class.add(account=account, password=password, cookie=cookie)
            logging.info(f"hao_yang_mao_class.add: {account}.")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
