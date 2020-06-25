import time
import asyncio
from config import g
from typing import List
from utils.biliapi import BiliApi
from config.log4 import crontab_task_logger as logging
from db.queries import queries, LTUser


async def main():
    start_prompt = f"Start do sign task"
    print(start_prompt)

    split_char_len = (100 - len(start_prompt)) // 2
    split_char = f"{'-' * split_char_len}"
    logging_msg_list = [
        f"\n{split_char}{start_prompt}{split_char}\n\n",
    ]
    start_time = time.time()
    lt_users: List[LTUser] = await queries.get_lt_user_by(available=True)

    for lt_user in lt_users:
        _m = f"Now proc {lt_user.name}(uid: {lt_user.DedeUserID}): \n"
        print(_m)
        logging_msg_list.append(_m)

        cookie = lt_user.cookie
        flag, result = await BiliApi.do_sign(cookie)
        if not flag and "请先登录" in result:
            logging_msg_list.append(
                f"WARNING: Do sign failed, user: {lt_user.name} - {lt_user.DedeUserID}, "
                f"flag: {flag}, result: {result}\n"
            )
            await queries.set_lt_user_invalid(lt_user=lt_user)
            continue

        flag, is_vip = await BiliApi.get_if_user_is_live_vip(cookie)
        if flag:
            if is_vip != lt_user.is_vip:
                await queries.set_lt_user_if_is_vip(lt_user=lt_user, is_vip=is_vip)
        else:
            logging_msg_list.append(
                f"WARNING: Get if it is vip failed, user: {lt_user.name} - {lt_user.DedeUserID}, "
                f"flag: {flag}, is_vip: {is_vip}\n"
            )

        r, data = await BiliApi.do_sign_group(cookie)
        if not r:
            logging_msg_list.append(f"ERROR: Sign group failed, {lt_user.name}-{lt_user.DedeUserID}: {data}\n")

        await BiliApi.do_sign_double_watch(cookie)

        if lt_user.DedeUserID == g.BILI_UID_DD:
            # 触发领取今日辣条
            await BiliApi.silver_to_coin(cookie)
            await BiliApi.get_bag_list(cookie=cookie)
            await BiliApi.receive_daily_bag(cookie=cookie)
        logging_msg_list.append("\tSuccess !\n")

    logging_msg_list.append(f"\nDo sign task done. cost: {int((time.time() - start_time) *1000)} ms.\n")
    logging_msg_list.append(f"{'-'*100}")
    logging.info("".join(logging_msg_list))


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

