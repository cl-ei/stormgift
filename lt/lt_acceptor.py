import time
import json
import random
import asyncio
import aiohttp
import traceback
from typing import Tuple, Any, Iterable
from config import cloud_acceptors, g
from config.log4 import acceptor_logger as logging
from db.tables import RaffleBroadCast
from db.queries import queries
from utils.cq import async_zy
from utils.dao import DelayAcceptGiftsQueue
from utils.dao import RedisCache, UserRaffleRecord

from config import REDIS_CONFIG, config
REDIS_CONFIG["db"] = int(config["redis"]["stormgift_db"])
redis_cache = RedisCache(**REDIS_CONFIG)


NON_SKIP_USER_ID = [
    20932326,  # DD
    39748080,  # LP
]
delay_accept_q = asyncio.Queue()
URLS_AND_412_TIME = {url: 0 for url in cloud_acceptors}


class BatchLotteryNotice:
    lottery_room_gift_to_count = {
        # "1008$gift_name": count
        # ...
    }
    room_update_time = {
        # "1008$gift_name": time.time()
    }
    threshold = 20

    @classmethod
    def add(cls, room_id, gift_name):
        key = f"{room_id}${gift_name}"
        if key in cls.lottery_room_gift_to_count:
            cls.lottery_room_gift_to_count[key] += 1
        else:
            cls.lottery_room_gift_to_count[key] = 1
        cls.room_update_time[key] = time.time()

    @classmethod
    def get(cls):
        result = []
        pop_keys = []
        for key, update_time in cls.room_update_time.items():
            delay = time.time() - update_time
            if delay > 3:
                count = cls.lottery_room_gift_to_count[key]
                if count >= cls.threshold:
                    room_id, gift_name = key.split("$", 1)
                    result.append((room_id, gift_name, count))
                pop_keys.append(key)

        for key in pop_keys:
            cls.room_update_time.pop(key)
            cls.lottery_room_gift_to_count.pop(key)
        return result


async def notice_qq():
    while True:
        result = BatchLotteryNotice.get()
        for r in result:
            room_id, gift_name, count = r
            await async_zy.send_group_msg(
                group_id=g.QQ_GROUP_井,
                message=(
                    f"{room_id}直播间 -> {count}个{gift_name}，快来领取吧~\n\n"
                    f"https://live.bilibili.com/{room_id}"
                )
            )
        await asyncio.sleep(1)


async def post_accept_request(
        act,
        room_id: int,
        gift_id: int,
        cookies: str,
        gift_type: str
) -> Tuple[bool, Any, str]:
    """

    return
    ------
    flag: bool

    result: list

    cloud_url: str
    """
    cloud_urls = []

    for url, time_412 in URLS_AND_412_TIME.items():
        if time.time() - time_412 > 20*60:
            cloud_urls.append(url)
    if not cloud_urls:
        cloud_url = random.choice(URLS_AND_412_TIME.keys())
        logging.error("No usable url! now force choose ome!")
    else:
        cloud_url = random.choice(cloud_urls)

    req_json = {
        "act": act,
        "room_id": room_id,
        "gift_id": gift_id,
        "cookies": cookies,
        "gift_type": gift_type,
    }
    client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    try:
        async with client_session as session:
            async with session.post(cloud_url, json=req_json) as resp:
                status_code = resp.status
                response = await resp.text()
                if status_code != 200:
                    return False, f"Cloud Function Error! [{response}]", cloud_url

                return_data = json.loads(response)
    except Exception as e:
        return False, f"Cloud Function Connection Error: {e}", cloud_url

    count_412 = 0
    for flag, message in return_data:
        if not flag and "412" in message:
            count_412 += 1
            if count_412 > 3:
                URLS_AND_412_TIME[cloud_url] = time.time()
                return False, "412", cloud_url

    URLS_AND_412_TIME[cloud_url] = 0
    return True, return_data, cloud_url


async def accept(
        index: int,
        act: str,
        room_id: int,
        gift_id: int,
        gift_type: str,
        gift_name: str,
):
    filter_k = {
        "join_tv_v5": "percent_tv",
        "join_guard": "percent_guard",
        "join_pk": "percent_pk",
    }[act]

    lt_users = await queries.get_lt_user_by(
        available=True,
        is_blocked=False,
        filter_k=filter_k
    )
    if not lt_users:
        return

    run_params = {
        "act": act,
        "room_id": room_id,
        "gift_id": gift_id,
        "cookies": [c.cookie for c in lt_users],
        "gift_type": gift_type
    }
    flag, result, cloud_acceptor_url = await post_accept_request(**run_params)
    if not flag and result == "412":
        flag, result, cloud_acceptor_url = await post_accept_request(**run_params)

    if not flag:
        logging.error(f"Accept Failed! {cloud_acceptor_url[-20:]} -> e: {result}")
        return

    success = []
    failed = []
    for index, lt_user in enumerate(lt_users):
        flag, message = result[index]

        if flag is not True:
            if "访问被拒绝" in message:
                await queries.set_lt_user_blocked(lt_user=lt_user)
            elif "请先登录哦" in message:
                await queries.set_lt_user_invalid(lt_user=lt_user)

            if index != 0:
                message = message[:100]
            failed.append(f"{lt_user.name}({lt_user.uid}){message}")
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

        await UserRaffleRecord.create(lt_user.uid, gift_name, gift_id, intimacy=award_num)
        await queries.set_lt_user_last_accept(lt_user)
        success.append(f"{lt_user.name}({lt_user.uid})")

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
        f"\nWorker: {index}, cloud_acceptor: {cloud_acceptor_url[-20:]}, total: {len(success)}\n"
        f"{'-'*80}"
    )


async def interval_assign_task(task_q):
    while True:
        task_params = await DelayAcceptGiftsQueue.get()
        for p in task_params:
            task_q.put_nowait(p)

        await asyncio.sleep(4)


class AcceptorClient:
    def __init__(self):
        self._workers = []
        self._param_q = asyncio.queues.Queue()

    @staticmethod
    async def receive():

        async def parse_one(rf: RaffleBroadCast, now_ts: float):
            if rf.raffle_type == "tv":
                BatchLotteryNotice.add(
                    room_id=rf.real_room_id,
                    gift_name=rf.gift_name
                )

                act = "join_tv_v5"
                accept_start_time = now_ts + rf.time_wait
                accept_end_time = now_ts + rf.max_time - 20
                wait_time = int(
                    (accept_end_time - accept_start_time)
                    * random.random()
                )
                implement_time = accept_start_time + wait_time

            elif rf.raffle_type == "guard":
                act = "join_guard"
                implement_time = now_ts + random.randint(60, 300)

            elif rf.raffle_type == "pk":
                act = "join_pk"
                implement_time = now_ts
            else:
                return

            await DelayAcceptGiftsQueue.put(
                data={
                    "act": act,
                    "room_id": rf.real_room_id,
                    "gift_id": rf.raffle_id,
                    "gift_type": rf.gift_type,
                    "gift_name": rf.gift_name,
                },
                accept_time=implement_time
            )
            await redis_cache.set("LT_LAST_ACTIVE_TIME", value=int(time.time()))
            logging.info(f"Assign: {rf} {time.time() - implement_time:.3f}秒后.")

        while True:
            pl_type = Iterable[Tuple[RaffleBroadCast, float]]
            prize_list: pl_type = await RaffleBroadCast.get(redis=redis_cache)
            for raffle, st in prize_list:
                logging.info(f"Raffle source received: {raffle}")
                await parse_one(raffle, st)
            await asyncio.sleep(10)

    async def accept_one(self, index: int):
        while True:
            params = await self._param_q.get()
            start_time = time.time()
            try:
                await accept(index, **params)
            except Exception as e:
                logging.error(f"ACCEPTOR worker[{index}] error: {e}\n{traceback.format_exc()}")

            cost_time = time.time() - start_time
            if cost_time > 5:
                logging.warning(f"ACCEPTOR worker[{index}] exec long time: {cost_time:.3f}")

    async def work(self):
        async def assign(task_q):
            while True:
                task_params = await DelayAcceptGiftsQueue.get()
                for p in task_params:
                    task_q.put_nowait(p)
                await asyncio.sleep(4)

        self._workers.append(asyncio.create_task(assign(self._param_q)))
        self._workers.extend([
            asyncio.create_task(self.accept_one(i))
            for i in range(128)
        ])
        for t in self._workers:
            await t


async def main():
    logging.info(f"\n{'-' * 80}\nLT ACCEPTOR started!\n{'-' * 80}")

    client = AcceptorClient()
    await asyncio.gather(
        notice_qq(),
        client.receive(),
        client.work(),
    )


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
