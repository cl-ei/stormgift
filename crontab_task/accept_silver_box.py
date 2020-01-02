import time
import datetime
from random import randint
import asyncio
from utils.biliapi import BiliApi
from config.log4 import silver_box_logger as logging
from utils.highlevel_api import DBCookieOperator
from utils.dao import UserRaffleRecord, redis_cache


class UserSilverAcceptTimeCtrl:
    key = "LT_SILVER_TIME_CTL"

    def __init__(self, user_obj):
        self.user = user_obj
        self.key_for_user = f"{self.key}_{datetime.datetime.today().date()}_{self.user.uid}"

    async def _get_accept_time(self):
        """

        :return: r:
            -1  done
            -2  skip
            >0  wait seconds
        """
        r = await redis_cache.get(self.key_for_user)
        if isinstance(r, int):
            return r

        flag, data = await BiliApi.check_silver_box(cookie=self.user.cookie)
        if not flag:
            logging.error(f"{self.user.name}({self.user.uid}) Cannot check_silver_box! error: {data}！")
            return -2

        code = data['code']
        if code == -10017:
            await redis_cache.set(key=self.key_for_user, value=-1, timeout=24 * 3600)
            logging.info(f"{self.user.name}({self.user.uid}) 今日宝箱领取完毕！现在退出。")
            return -1

        elif code == -500:
            await DBCookieOperator.set_invalid(self.user)
            return -2

        elif code == 0:
            accept_time = data["data"]["time_end"]
            await redis_cache.set(key=self.key_for_user, value=accept_time, timeout=24 * 3600)
            logging.info(f"{self.user.name}({self.user.uid}) 从API获取到下次领取宝箱时间: {accept_time - time.time():.3f}")
            return accept_time

        logging.error(f"不能从API获取下次领取时间！data: {data}")
        return -2

    async def _post_accept_req(self):
        user = self.user
        flag, data = await BiliApi.join_silver_box(cookie=user.cookie, access_token=user.access_token)
        if not flag:
            logging.error(f"{user.name}(uid: {user.uid})  Join silver box failed! {data}")
            return

        error_message = data.get("message", "")
        if "请先登录" in error_message:
            await DBCookieOperator.set_invalid(user)
            logging.info(f"DBCookieOperator refresh token: {flag}, msg: {data}")
            return

        code = data['code']
        if code == 0:
            award_silver = data["data"]["awardSilver"]
            raffle_id = int(f"313{randint(100000, 999999)}")
            await UserRaffleRecord.create(user.uid, "宝箱", raffle_id=raffle_id, intimacy=award_silver)
            logging.info(f"{user.name}(uid: {user.uid}) 打开了宝箱. award_silver: {award_silver}")

        elif code == -500:
            sleep_time = data['data']['surplus'] * 60 + 5
            logging.error(f"{user.name}({user.uid}) 发生了不期待的结果：继续等待宝箱冷却, surplus: {int(sleep_time)}.")

        elif code == 400:
            logging.info(f"{user.name}(uid: {user.uid}) 宝箱开启中返回了小黑屋提示.")
            await redis_cache.set(self.key_for_user, value=-1, timeout=24*3600)

        elif code == -800:
            logging.info(f'{user.name}(uid: {user.uid}) 未绑定手机!')
            await redis_cache.set(self.key_for_user, value=-1, timeout=24 * 3600)

        else:
            logging.error(f'领取宝箱时发生Unknown Error, code {code}, data: {data}')
            return

    async def accept(self):
        accept_time = await self._get_accept_time()
        if accept_time < 0:
            return accept_time

        interval = accept_time - time.time()
        if interval > 0:
            logging.info(f"{self.user.name}({self.user.uid}) 领取时间未到，sleep: {interval:.3f}.")
            return accept_time

        await redis_cache.delete(self.key_for_user)
        await self._post_accept_req()
        await asyncio.sleep(5)

        accept_time = await self._get_accept_time()
        await asyncio.sleep(5)
        return accept_time


async def main():
    start_time = time.time()
    today_key = F"LT_SILVER_BOX_ALL_DONE_{datetime.datetime.today().date()}"
    if await redis_cache.get(today_key):
        return

    objs = await DBCookieOperator.get_objs(available=True, non_blocked=True)
    logging.info(f"Now start silver box task. users: {len(objs)}")

    result_list = []
    for user in objs:
        a = UserSilverAcceptTimeCtrl(user_obj=user)
        r = await a.accept()
        if r == -1:
            result_list.append(user)

    if len(result_list) == len(objs):
        await redis_cache.set(today_key, value=int(time.time()), timeout=3600*24)
        logging.info(f"Silver box ALL_DONE!")
    else:
        logging.info(
            f"Silver box task done. "
            f"finished {len(result_list)}/{len(objs)}, cost: {time.time() - start_time:.3f}"
        )


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
