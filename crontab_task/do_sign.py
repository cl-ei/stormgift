import time
import asyncio
from utils.biliapi import BiliApi
from utils.highlevel_api import DBCookieOperator
from config.log4 import crontab_task_logger as logging


async def main():
    start_prompt = f"Start do sign task"
    split_char_len = (100 - len(start_prompt)) // 2
    split_char = f"{'-' * split_char_len}"
    logging_msg_list = [
        f"{split_char}{start_prompt}{split_char}\n",
    ]
    start_time = time.time()
    objs = await DBCookieOperator.get_objs(available=True)

    for obj in objs:
        logging_msg_list.append(f"\nNow proc {obj.name}(uid: {obj.DedeUserID}).\n")

        cookie = obj.cookie
        flag, result = await BiliApi.do_sign(cookie)
        if not flag and "请先登录" in result:
            logging_msg_list.append(
                f"WARNING: Do sign failed, user: {obj.name} - {obj.DedeUserID}, "
                f"flag: {flag}, result: {result}\n"
            )
            await DBCookieOperator.set_invalid(obj)
            continue

        await asyncio.sleep(0.5)

        flag, is_vip = await BiliApi.get_if_user_is_live_vip(cookie)
        if flag:
            if is_vip != obj.is_vip:
                await DBCookieOperator.set_vip(obj, is_vip)
        else:
            logging_msg_list.append(
                f"WARNING: Get if it is vip failed, user: {obj.name} - {obj.DedeUserID}, "
                f"flag: {flag}, is_vip: {is_vip}\n"
            )

        await asyncio.sleep(0.5)

        r, data = await BiliApi.do_sign_group(cookie)
        if not r:
            logging_msg_list.append(f"ERROR: Sign group failed, {obj.name}-{obj.DedeUserID}: {data}\n")

        await asyncio.sleep(0.5)
        await BiliApi.do_sign_double_watch(cookie)

        if obj.DedeUserID == 20932326:
            await asyncio.sleep(0.5)
            await BiliApi.silver_to_coin(cookie)

        # 触发领取今日辣条
        await BiliApi.get_bag_list(cookie=cookie)
    logging_msg_list.append(f"\nDo sign task done. cost: {int((time.time() - start_time) *1000)} ms.\n")
    logging_msg_list.append(f"{'-'*100}")
    logging.info("".join(logging_msg_list))


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

