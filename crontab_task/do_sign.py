import time
import asyncio
from utils.biliapi import BiliApi
from utils.highlevel_api import DBCookieOperator
from config.log4 import crontab_task_logger as logging


async def main():
    logging.info(f"Start do sign task.")
    start_time = time.time()
    objs = await DBCookieOperator.get_objs(available=True)

    for obj in objs:

        logging.info(f"Now proc {obj.name}(uid: {obj.DedeUserID}).")

        cookie = obj.cookie
        flag, result = await BiliApi.do_sign(cookie)
        if not flag and "请先登录" in result:
            logging.warn(f"Do sign failed, user: {obj.name} - {obj.DedeUserID} flag: {flag}, result: {result}")
            await DBCookieOperator.set_invalid(obj)
            continue

        await asyncio.sleep(0.5)

        flag, is_vip = await BiliApi.get_if_user_is_live_vip(cookie)
        if flag:
            if is_vip != obj.is_vip:
                await DBCookieOperator.set_vip(obj, is_vip)
        else:
            logging.warn(f"Get if it is vip failed, user: {obj.name} - {obj.DedeUserID} flag: {flag}, is_vip: {is_vip}")

        await asyncio.sleep(0.5)

        r, data = await BiliApi.do_sign_group(cookie)
        if not r:
            logging.error(f"Sign group failed, {obj.name}-{obj.DedeUserID}: {data}")

        await asyncio.sleep(0.5)
        await BiliApi.do_sign_double_watch(cookie)

        if obj.DedeUserID == 20932326:
            await asyncio.sleep(0.5)
            await BiliApi.silver_to_coin(cookie)

    logging.info(f"Do sign task done. cost: {int((time.time() - start_time) *1000)} ms.\n\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

