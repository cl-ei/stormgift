import sys
import time
import json
import random
import asyncio
import aiohttp
import datetime
import traceback
from config import cloud_acceptors
from utils.mq import mq_raffle_to_acceptor
from utils.highlevel_api import DBCookieOperator
from config.log4 import acceptor_logger as logging
from utils.dao import (
    redis_cache,
    LTTempBlack,
    LTUserSettings,
    UserRaffleRecord,
    LTLastAcceptTime,
    StormGiftBlackRoom,
    DelayAcceptGiftsMQ,
)

NON_SKIP_USER_ID = [
    20932326,  # DD
    39748080,  # LP
]
delay_accept_q = asyncio.Queue()


async def async_post(url, data=None, json=None, headers=None, timeout=30):
    client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))
    try:
        async with client_session as session:
            async with session.post(url, data=data, json=json, headers=headers) as resp:
                status_code = resp.status
                content = await resp.text()
                return status_code, content

    except Exception as e:
        return 5000, f"Error in request: {e}"


class Worker(object):
    def __init__(self, index):
        self.worker_index = index
        self.__busy_time = 0

        self._cookie_objs = []
        self._cookie_objs_update_time = 0

    async def load_cookie(self):
        if time.time() - self._cookie_objs_update_time > 100:
            self._cookie_objs = await DBCookieOperator.get_objs(available=True, non_blocked=True)
            self._cookie_objs_update_time = time.time()

        return self._cookie_objs

    async def proc_single(self, key):
        await redis_cache.set("LT_LAST_ACTIVE_TIME", value=int(time.time()))

        key_type, room_id, gift_id, *other_args = key.split("$")
        room_id = int(room_id)
        gift_id = int(gift_id)
        gift_type = ""

        cookie_objs = await self.load_cookie()
        # temporary_blocked = await LTTempBlack.get_blocked()
        # cookie_objs = [c for c in cookie_objs if c.uid not in temporary_blocked]

        if key_type == "T":
            gift_type, *_ = other_args
            act, filter_k = "join_tv_v5", "tv_percent"
        elif key_type == "G":
            act, filter_k = "join_guard", "guard_percent"
        elif key_type == "P":
            act, filter_k = "join_pk", "pk_percent"
        elif key_type == "A":
            act, filter_k = "join_anchor", "anchor_percent"
        else:
            return

        user_cookie_objs = await LTUserSettings.filter_cookie(cookie_objs, key=filter_k)
        if not user_cookie_objs:
            return

        req_json = {
            "act": act,
            "room_id": room_id,
            "gift_id": gift_id,
            "cookies": [c.cookie for c in user_cookie_objs],
            "gift_type": gift_type,
        }
        cloud_acceptor_url = random.choice(cloud_acceptors)
        status_code, content = await async_post(url=cloud_acceptor_url, json=req_json)
        if status_code != 200:
            return logging.error(f"Accept Failed! e: {content}")

        result_list = json.loads(content)
        if act == "join_pk":
            gift_name = "PK"
        elif act == "join_tv_v5":
            gift_name = await redis_cache.get(key=f"GIFT_TYPE_{gift_type}")
            gift_name = gift_name or "高能"
        elif act == "join_guard":
            info = await redis_cache.get(f"G${room_id}${gift_id}")
            privilege_type = info["privilege_type"]
            if privilege_type == 3:
                gift_name = "舰长"
            elif privilege_type == 2:
                gift_name = "提督"
            elif privilege_type == 1:
                gift_name = "总督"
            else:
                gift_name = "大航海"
        elif act == "join_storm":
            gift_name = "节奏风暴"
        elif act == "join_anchor":
            gift_name = "天选时刻"
        else:
            gift_name = "未知"
        gift_name = gift_name.replace("抽奖", "")

        success = []
        success_uid_list = []
        failed = []
        for index, cookie_obj in enumerate(user_cookie_objs):
            flag, message = result_list[index]

            if flag is not True:
                if "访问被拒绝" in message:
                    await DBCookieOperator.set_blocked(cookie_obj)
                    self._cookie_objs_update_time = 0
                elif "请先登录哦" in message:
                    await DBCookieOperator.set_invalid(cookie_obj)
                    self._cookie_objs_update_time = 0
                elif act == "join_storm" and "验证码没通过" in message:
                    logging.warning(f"{cookie_obj.name}(uid: {cookie_obj.uid}) {message}. set blocked.")
                    await StormGiftBlackRoom.set_blocked(cookie_obj.uid)
                elif "你已经领取过" in message or "您已参加抽奖" in message:
                    await LTTempBlack.manual_accept_once(uid=cookie_obj.uid)

                if index != 0:
                    message = message[:100]
                failed.append(f"{cookie_obj.name}({cookie_obj.uid}){message}")
                continue

            try:
                award_num, award_name = message.split("_", 1)
                award_num = int(award_num)
                if award_name in ("辣条", "亲密度"):
                    pass
                elif award_name in ("银瓜子", "金瓜子"):
                    award_num //= 100
                else:
                    award_num = 0

            except Exception as e:
                logging.error(f"Cannot fetch award_num from message. {e}", exc_info=True)
                award_num = 1

            await UserRaffleRecord.create(cookie_obj.uid, gift_name, gift_id, intimacy=award_num)
            success.append(f"{cookie_obj.name}({cookie_obj.uid})")
            success_uid_list.append(cookie_obj.uid)

        await LTLastAcceptTime.update(*success_uid_list)

        success_users = []
        for i, s in enumerate(success):
            success_users.append(s)
            if i > 0 and i % 4 == 0:
                success_users.append("\n")
        success_users = "".join(success_users)
        failed_prompt = f"{'-'*20} FAILED {'-'*20}\n{'^'.join(failed)}\n" if failed else ""
        title = f"{act.upper()} OK {gift_name} @{room_id}${gift_id}"
        split_char_count = max(0, (80 - len(title)) // 2)
        logging.info(
            f"\n{'-'*split_char_count}{title}{'-'*split_char_count}\n"
            f"{success_users}\n"
            f"{failed_prompt}"
            f"\nWorker: {self.worker_index}, cloud_acceptor: {cloud_acceptor_url[-20:]}, total: {len(success)}\n"
            f"{'-'*80}"
        )

    async def accept_guard(self):
        while True:
            message = await mq_raffle_to_acceptor.get()

            start_time = time.time()
            task_id = f"{int(str(random.random())[2:]):x}"
            try:
                r = await self.proc_single(message)
            except Exception as e:
                logging.error(f"Acceptor Task {self.worker_index}-[{task_id}] error: {e}, {traceback.format_exc()}")
                continue

            cost_time = time.time() - start_time
            if cost_time > 5:
                logging.info(f"Acceptor Task {self.worker_index}-[{task_id}] success, r: {r}, cost: {cost_time:.3f}")

    async def accept_delayed(self):
        while True:
            message = await delay_accept_q.get()
            start_time = time.time()
            task_id = f"{int(str(random.random())[2:]):x}"
            try:
                r = await self.proc_single(message)
            except Exception as e:
                logging.error(f"DELAY Acceptor {self.worker_index}-[{task_id}] error: {e}, {traceback.format_exc()}")
                continue

            cost_time = time.time() - start_time
            if cost_time > 5:
                logging.info(f"DELAY Acceptor {self.worker_index}-[{task_id}] success, r: {r}, cost: {cost_time:.3f}")

    @staticmethod
    async def monitor_delayed():
        while True:
            messages = await DelayAcceptGiftsMQ.get()
            if not messages:
                await asyncio.sleep(3)
                continue

            for m in messages:
                logging.info(f"monitor_delayed find key: {m}")
                delay_accept_q.put_nowait(m)


async def main():
    logging.info("-" * 80)
    logging.info("LT ACCEPTOR started!")
    logging.info("-" * 80)

    tasks = [asyncio.create_task(Worker(index).accept_guard()) for index in range(8)]
    delays = [asyncio.create_task(Worker(100 + index).accept_delayed()) for index in range(32)]

    await Worker(1001).monitor_delayed()
    for t in tasks + delays:
        await t

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
