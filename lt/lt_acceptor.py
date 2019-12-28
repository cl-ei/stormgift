import sys
import time
import json
import random
import asyncio
import aiohttp
import datetime
import traceback
from utils.ws import RCWebSocketClient
from config import cloud_acceptors
from utils.highlevel_api import DBCookieOperator
from utils.dao import DelayAcceptGiftsQueue
from config.log4 import acceptor_logger as logging
from utils.dao import (
    redis_cache,
    LTTempBlack,
    LTUserSettings,
    UserRaffleRecord,
    LTLastAcceptTime,
    StormGiftBlackRoom,
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
    def __init__(self, index, q):
        self.worker_index = index
        self.q = q
        self.__busy_time = 0

        self._cookie_objs = []
        self._cookie_objs_update_time = 0

    async def load_cookie(self):
        if time.time() - self._cookie_objs_update_time > 100:
            self._cookie_objs = await DBCookieOperator.get_objs(available=True, non_blocked=True)
            self._cookie_objs_update_time = time.time()

        return self._cookie_objs

    async def proc_single(self, data):
        await redis_cache.set("LT_LAST_ACTIVE_TIME", value=int(time.time()))

        raffle_type = data.get("raffle_type")
        room_id = data.get("real_room_id")
        gift_id = data.get("raffle_id")
        gift_type = data.get("gift_type", "")
        gift_name = data.get("gift_name", "未知")

        cookie_objs = await self.load_cookie()
        # temporary_blocked = await LTTempBlack.get_blocked()
        # cookie_objs = [c for c in cookie_objs if c.uid not in temporary_blocked]

        if raffle_type == "tv":
            act, filter_k = "join_tv_v5", "tv_percent"
        elif raffle_type == "guard":
            act, filter_k = "join_guard", "guard_percent"
        elif raffle_type == "pk":
            act, filter_k = "join_pk", "pk_percent"
        elif raffle_type == "anchor":
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

    async def accept_delayed(self):
        while True:
            data = await self.q.get()
            start_time = time.time()
            try:
                r = await self.proc_single(data)
            except Exception as e:
                logging.error(f"DELAY Acceptor {self.worker_index}. error: {e}, {traceback.format_exc()}")
                continue

            cost_time = time.time() - start_time
            if cost_time > 5:
                logging.info(f"DELAY Acceptor {self.worker_index} success, r: {r}, cost: {cost_time:.3f}")


async def main():
    logging.info("-" * 80)
    logging.info("LT ACCEPTOR started!")
    logging.info("-" * 80)

    async def nop(*args, **kw):
        pass

    async def on_message(message):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        raffle_type = data.get("raffle_type")
        now = int(time.time())
        ts = data.get("ts", now)

        if raffle_type in ("anchor", "storm"):
            return
        elif raffle_type == "tv":
            time_wait = data["time_wait"]
            max_time = data["max_time"]
            accept_start_time = ts + time_wait
            accept_end_time = ts + max_time
            wait_time = int((accept_end_time - accept_start_time - 8) * random.random())
            recommended_implementation_time = accept_start_time + wait_time
        elif raffle_type == "guard":
            recommended_implementation_time = ts + random.randint(60, 600)
        else:
            recommended_implementation_time = now

        print(f"received. delay: {recommended_implementation_time - ts:.0f} -> {data}.")
        await DelayAcceptGiftsQueue.put(data, recommended_implementation_time)

    new_client = RCWebSocketClient(
        url="wss://www.madliar.com/raffle_wss",
        on_message=on_message,
        on_connect=nop,
        on_shut_down=nop,
        heart_beat_pkg="a",
        heart_beat_interval=300
    )
    await new_client.start()

    monitor_q = asyncio.Queue()

    async def select_task():
        while True:
            raffle_tasks = await DelayAcceptGiftsQueue.get()
            for t in raffle_tasks:
                monitor_q.put_nowait(t)
            await asyncio.sleep(4)

    tasks = [asyncio.create_task(select_task())]
    tasks += [
        asyncio.create_task(Worker(100 + index, monitor_q).accept_delayed())
        for index in range(128)
    ]
    await asyncio.gather(*tasks)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
