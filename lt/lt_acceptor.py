import sys
import time
import json
import asyncio
import requests
import traceback
from random import random
from utils.dao import redis_cache, AlternativeLtDetection
from config import cloud_acceptor_url
from utils.mq import mq_raffle_to_acceptor
from utils.highlevel_api import DBCookieOperator
from config.log4 import acceptor_logger as logging
from utils.reconstruction_model import UserRaffleRecord, objects


NON_SKIP_USER_ID = [
    20932326,  # DD
    39748080,  # LP
]
delay_accept_q = asyncio.Queue()


class Worker(object):
    def __init__(self, index):
        self.worker_index = index
        self.__busy_time = 0
        self.accepted_keys = []

        self._cookie_objs_non_skip = []
        self._cookie_objs = []
        self._cookie_objs_update_time = 0

    def _is_new_gift(self, *args):
        key = "$".join([str(_) for _ in args])
        if key in self.accepted_keys:
            return False

        self.accepted_keys.insert(0, key)

        while len(self.accepted_keys) >= 10000:
            self.accepted_keys.pop()

        return True

    async def load_cookie(self):
        if time.time() - self._cookie_objs_update_time > 100:
            objs = await DBCookieOperator.get_objs(available=True, non_blocked=True, separate=True)
            self._cookie_objs_non_skip, self._cookie_objs = objs
            self._cookie_objs_update_time = time.time()

        return self._cookie_objs_non_skip, self._cookie_objs

    async def proc_single(self, key):
        key_type, room_id, gift_id, *other_args = key.split("$")
        room_id = int(room_id)
        gift_id = int(gift_id)
        if not self._is_new_gift(key_type, room_id, gift_id):
            return "Repeated gift, skip it."
        gift_type = ""

        if key_type == "T":
            gift_type, accept_time, *_ = other_args
            delay_accept_q.put_nowait((room_id, gift_id, gift_type, int(accept_time)))
            return
        elif key_type == "T_NOW":
            gift_type, *_ = other_args
            act = "join_tv_v5"
        elif key_type == "G":
            act = "join_guard"
        elif key_type == "P":
            act = "join_pk"
        else:
            return

        non_skip, normal_objs = await self.load_cookie()
        alternative_uid_list = await AlternativeLtDetection.get_blocked_list(*[nr.uid for nr in normal_objs])
        filtered_normal_objs = []
        alternative_uid_list_prompt = []
        for nr in normal_objs:
            if nr.uid in alternative_uid_list:
                alternative_uid_list_prompt.append(f"{nr.name}(uid: {nr.uid})")
            else:
                filtered_normal_objs.append(nr)
        if alternative_uid_list_prompt:
            alternative_uid_list_prompt = ", ".join(alternative_uid_list_prompt)
            logging.info(f"Find alternative uid list: {alternative_uid_list_prompt}.")

        user_cookie_objs = non_skip + filtered_normal_objs
        cookies = [c.cookie for c in user_cookie_objs]

        req_json = {
            "act": act,
            "room_id": room_id,
            "gift_id": gift_id,
            "cookies": cookies,
            "gift_type": gift_type,
        }
        try:
            r = requests.post(url=cloud_acceptor_url, json=req_json, timeout=20)
        except Exception as e:
            logging.error(f"Cannot access cloud acceptor! e: {e}")
            return

        if r.status_code != 200:
            return logging.error(f"Accept Failed! e: {r.content.decode('utf-8')}")

        result_list = json.loads(r.content.decode('utf-8'))
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
        else:
            gift_name = "未知"
        gift_name = gift_name.replace("抽奖", "")

        index = 0
        success = []
        last_raffle_id = None
        for cookie_obj in user_cookie_objs:
            flag, message = result_list[index]
            index += 1

            if flag is not True:
                if "访问被拒绝" in message:
                    await DBCookieOperator.set_blocked(cookie_obj)
                    self._cookie_objs_update_time = 0
                elif "请先登录哦" in message:
                    await DBCookieOperator.set_invalid(cookie_obj)
                    self._cookie_objs_update_time = 0

                if index != 0:
                    message = message[:100]
                logging.warning(
                    f"{act.upper()} FAILED! {index}-{cookie_obj.name}({cookie_obj.uid}) "
                    f"@{room_id}${gift_id}, message: {message}"
                )
                continue

            try:
                award_num = int(message.split("_", 1)[0])
            except Exception as e:
                logging.error(f"Cannot fetch award_num from message. {e}", exc_info=True)
                award_num = 1

            r = await UserRaffleRecord.create(cookie_obj.uid, gift_name, gift_id, intimacy=award_num)
            last_raffle_id = r.id
            success.append(f"{message} <- {index}-{cookie_obj.uid}-{cookie_obj.name}")

            if "你已经领取过啦" in message or "已经参加抽奖" in message:
                await AlternativeLtDetection.record(cookie_obj.uid)

        success_users = "\n".join(success)
        title = f"{act.upper()} OK {gift_name} @{room_id}${gift_id}"
        split_char_count = max(0, (80 - len(title)) // 2)
        logging.info(
            f"\n{'-'*split_char_count}{title}{'-'*split_char_count}\n"
            f"{success_users}\n\n"
            f"last_raffle_id: {last_raffle_id}\n"
            f"{'-'*80}"
        )

    async def waiting_delay_raffles(self):
        exec_interval = 5
        try:
            while True:
                start_time = time.time()

                tasks = [delay_accept_q.get_nowait() for _ in range(delay_accept_q.qsize())]
                execute_count = 0
                total = len(tasks)
                for task in tasks:
                    room_id, gift_id, gift_type, exec_time, *_ = task

                    if exec_time < start_time:
                        key = f"T_NOW${room_id}${gift_id}${gift_type}"
                        await mq_raffle_to_acceptor.put(key)
                        execute_count += 1
                    else:
                        delay_accept_q.put_nowait(task)

                end_time = time.time()
                sleep_time = start_time + exec_interval - end_time
                if total > 0:
                    logging.debug(
                        f"delay_raffles {self.worker_index}-sleep: {sleep_time:.3f}, "
                        f"exec: {execute_count}/{total}"
                    )
                await asyncio.sleep(max(sleep_time, 0))
        except Exception as e:
            logging.exception(f"Error happened in waiting_delay_raffles: {e}", exc_info=True)
            sys.exit(-1)

    async def run_forever(self):
        while True:
            message, has_read = await mq_raffle_to_acceptor.get()

            start_time = time.time()
            task_id = f"{int(str(random())[2:]):x}"
            logging.info(f"Acceptor Task {self.worker_index}-[{task_id}] start...")

            try:
                r = await self.proc_single(message)
            except Exception as e:
                logging.error(f"Acceptor Task {self.worker_index}-[{task_id}] error: {e}, {traceback.format_exc()}")
            else:
                cost_time = time.time() - start_time
                logging.info(f"Acceptor Task {self.worker_index}-[{task_id}] success, r: {r}, cost: {cost_time:.3f}")
            finally:
                await has_read()


async def main():
    logging.info("-" * 80)
    logging.info("LT ACCEPTOR started!")
    logging.info("-" * 80)
    await objects.connect()

    tasks = [asyncio.create_task(Worker(index).run_forever()) for index in range(4)]
    tasks.append(asyncio.create_task(Worker(99).waiting_delay_raffles()))
    for t in tasks:
        await t

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
