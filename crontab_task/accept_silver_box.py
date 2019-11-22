import time
from random import randint
import asyncio
from utils.biliapi import BiliApi
from config.log4 import silver_box_logger as logging
from utils.highlevel_api import DBCookieOperator
from utils.dao import UserRaffleRecord


async def accept(user):
    logging.info(f"Now proc {user.name}(uid: {user.uid})...")

    while True:
        flag, data = await BiliApi.check_silver_box(cookie=user.cookie)
        if not flag:
            logging.warning(f"{user.name}(uid: {user.uid}) Cannot check_silver_box! error: {data}！ 现在退出。")
            return

        code = data['code']
        if code == -10017:
            logging.info(f"{user.name}(uid: {user.uid}) 今日宝箱领取完毕！现在退出。")
            return

        if code != 0:
            await asyncio.sleep(60)
            continue

        flag, data = await BiliApi.join_silver_box(cookie=user.cookie, access_token=user.access_token)
        if not flag:
            logging.warning(f"{user.name}(uid: {user.uid})  Join silver box failed! {data}")
            await asyncio.sleep(60)
            continue

        error_message = data.get("message", "")
        if "请先登录" in error_message:
            flag, data = await DBCookieOperator.refresh_token(obj_or_user_id=user)
            if flag:
                logging.info(f"DBCookieOperator refresh token: {flag}, msg: {data}")
                continue
            else:
                logging.info(f"{user.name}(uid: {user.uid}) 不能刷新token! 现在退出。err msg: {data}")
                return

        code = data['code']
        if code == 0:
            award_silver = data["data"]["awardSilver"]
            raffle_id = int(f"313{randint(100000, 999999)}")
            await UserRaffleRecord.create(user.uid, "宝箱", raffle_id=raffle_id, intimacy=award_silver)
            logging.info(f"{user.name}(uid: {user.uid}) 打开了宝箱. award_silver: {award_silver}")

        elif code == -500:
            sleep_time = data['data']['surplus'] * 60 + 5
            logging.info(f"{user.name}(uid: {user.uid}) 继续等待宝箱冷却, sleep_time: {int(sleep_time)}.")
            await asyncio.sleep(sleep_time)

        elif code == -903:
            return

        elif code == 400:
            logging.info(f"{user.name}(uid: {user.uid}) 宝箱开启中返回了小黑屋提示.")
            return

        elif code == -800:
            logging.info(f'{user.name}(uid: {user.uid}) 未绑定手机!')
            return

        else:
            logging.warn(f'Unknown Error: {data}')
            return


async def main():
    objs = await DBCookieOperator.get_objs(available=True, non_blocked=True)
    tasks = [asyncio.create_task(accept(o)) for o in objs]
    for t in tasks:
        await t


loop = asyncio.get_event_loop()
loop.run_until_complete(main())


