import sys
import pickle
import traceback
import asyncio
import logging
from utils.biliapi import CookieFetcher
from config.log4 import console_logger as logging
from utils.biliapi import BiliApi
from utils.highlevel_api import DBCookieOperator


if sys.argv[-1] == "lm":
    from utils.dao import HYMCookies as hao_yang_mao_class
else:
    from utils.dao import HYMCookiesOfCl as hao_yang_mao_class


class H:
    def __init__(self, target):
        self.accounts = []
        self.cookies = []
        self.target = target

    async def login(self, account, password):
        flag, cookie = await CookieFetcher.get_cookie(account, password)
        if not flag:
            logging.error(f"▆▆IMPORTANT▆▆ Cannot get_cookie for account: {account}! message: {cookie}")
            return

        await hao_yang_mao_class.add(account=account, password=password, cookie=cookie)
        logging.info(f"▆▆IMPORTANT▆▆ {account} Success! {account}, pass: {password}")

    async def execute(self, proc_index, account, password, cookie):
        try_times = -1
        while try_times < 3:
            if isinstance(cookie, str):
                pass
            elif isinstance(cookie, dict) and "cookie" in cookie:
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
        account_info_dict = await hao_yang_mao_class.get(return_dict=True)
        proc_index = -1
        for account, info_dict in account_info_dict.items():
            password = info_dict["password"]
            cookie = info_dict["cookie"]
            proc_index += 1

            logging.info(f"\nAccount: {account}, pass: {password}.\n┏{'-' * 80}┓")
            await self.execute(proc_index, account, password, cookie)
            logging.info(f"end of proc: {proc_index}.\n┗{'-' * 80}┛")


async def sign_s9(proc_index, cookie):
    flag, msg = await BiliApi.join_s9_sign(cookie=cookie)
    logging.info(f"join_s9_sign: flag: {flag}, message: {msg}")


async def open_capsule(proc_index, cookie):
    flag, msg = await BiliApi.join_s9_open_capsule(cookie=cookie)
    logging.info(f"join_s9_open_capsule: flag: {flag}, message: {msg}")


async def receive_daily_bag(proc_index, cookie):
    r = await BiliApi.receive_daily_bag(cookie)
    logging.info(f"receive_daily_bag: {r}")


async def do_sign(proc_index, cookie):
    if cookie is None:
        logging.error(f"Bad cookie! {cookie}")
        return False, {"re_login": True}

    flag, result = await BiliApi.do_sign(cookie)
    if not flag and "请先登录" in result:
        logging.warning(f"Do sign failed. result: {result}")
        return False, {"re_login": True}
    logging.info("Sign success!")


card_list = {}


async def send(proc_index, cookie):
    # 送辣条！
    ruid = 20932326
    live_room_id = 13369254

    # 送头衔续期卡
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

        if "续期卡" in gift["gift_name"]:
            logging.info(f"发现头衔续期卡: f{gift['gift_name']}*{gift['gift_num']}")

            if gift["gift_name"] in card_list:
                card_list[gift["gift_name"]] += 1
            else:
                card_list[gift["gift_name"]] = 0

            card_record_id = gift["card_record_id"]
            num = gift["gift_num"]
            receive_uid = ruid
            r = await BiliApi.send_card(
                cookie=cookie,
                card_record_id=card_record_id,
                receive_uid=receive_uid,
                num=num
            )
            logging.info(f"Send card: {gift['gift_name']} r: {r}")


async def receive_mail_bags(user_id):
    user = await DBCookieOperator.get_by_uid(user_id)
    if not user:
        logging.error(f"Cannot find user: {user_id}")
        return

    flag, mail_list = await BiliApi.check_mail_box(user.cookie)
    if not flag:
        logging.error(f"Error: {mail_list}")
        return

    logging.info(f"Mails len: {len(mail_list)}")

    count = 0
    for mail in mail_list:
        count += 1
        mail_id = mail["mail_id"]
        r = await BiliApi.accept_gift_from_mail_box(user.cookie, mail_id=mail_id)
        logging.info(f"count: {count}, r: {mail_id} -> {r}")

    logging.info("End.")


async def renew_card_to_lm():
    user = await DBCookieOperator.get_by_uid("DD")
    bag_list = await BiliApi.get_bag_list(user.cookie)
    bags = [bag for bag in bag_list if "续期卡" in bag["gift_name"]]
    prompt = [f"{x['corner_mark']}-{x['gift_name']}*{x['gift_num']}" for x in bags]
    logging.info("获取到DD的包裹内：\n" + "\n".join(prompt))
    receive_uid = 6851677  # 雨声雷鸣
    for bag in bags:
        num = int(bag["gift_num"]*0.9)
        card_record_id = bag["card_record_id"]
        r = await BiliApi.send_card(
            cookie=user.cookie,
            card_record_id=card_record_id,
            receive_uid=receive_uid,
            num=num
        )
        logging.info(f"Send card: {bag['gift_name']}*{num}, r: {r}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "receive":
        loop = asyncio.get_event_loop()
        loop.run_until_complete(receive_mail_bags("DD"))
        sys.exit(0)
    elif cmd == "renew":
        loop = asyncio.get_event_loop()
        loop.run_until_complete(renew_card_to_lm())
        sys.exit(0)

    target = {
        "s9": sign_s9,
        "open_s9": open_capsule,
        "r": receive_daily_bag,
        "do_sign": do_sign,
        "send": send,
    }.get(cmd)

    hym = H(target=target)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(hym.run())
    logging.info(card_list)
