import time
import json
import random
import asyncio
import aiohttp
import traceback
from utils.cq import async_zy
from config import cloud_acceptors, g
from utils.highlevel_api import DBCookieOperator
from utils.dao import DelayAcceptGiftsQueue
from config.log4 import acceptor_logger as logging
from utils.dao import (
    redis_cache,
    LTUserSettings,
    UserRaffleRecord,
    LTLastAcceptTime,
)

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


async def cloud_accept(act, room_id, gift_id, cookies, gift_type):
    """

    RETURN: (flag, result, cloud_url)
        flag -> bool, result -> list
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
                if status_code != 200:
                    return False, "Cloud Function Error!", cloud_url

                return_data = json.loads(await resp.text())
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


async def accept(index, act, room_id, gift_id, gift_type, gift_name):
    cookie_objs = await DBCookieOperator.get_objs(available=True, non_blocked=True)
    # temporary_blocked = await LTTempBlack.get_blocked()
    # cookie_objs = [c for c in cookie_objs if c.uid not in temporary_blocked]

    filter_k = {
        "join_tv_v5": "tv_percent",
        "join_guard": "guard_percent",
        "join_pk": "pk_percent",
    }[act]

    user_cookie_objs = await LTUserSettings.filter_cookie(cookie_objs, key=filter_k)
    if not user_cookie_objs:
        return

    run_params = {
        "act": act,
        "room_id": room_id,
        "gift_id": gift_id,
        "cookies": [c.cookie for c in user_cookie_objs],
        "gift_type": gift_type
    }
    flag, result, cloud_acceptor_url = await cloud_accept(**run_params)
    if not flag and result == "412":
        flag, result, cloud_acceptor_url = await cloud_accept(**run_params)

    if not flag:
        logging.error(f"Accept Failed! e: {result}")
        return

    success = []
    success_uid_list = []
    failed = []
    for index, cookie_obj in enumerate(user_cookie_objs):
        flag, message = result[index]

        if flag is not True:
            if "访问被拒绝" in message:
                await DBCookieOperator.set_blocked(cookie_obj)
            elif "请先登录哦" in message:
                await DBCookieOperator.set_invalid(cookie_obj)
            # elif "你已经领取过" in message or "您已参加抽奖" in message:
            #     await LTTempBlack.manual_accept_once(uid=cookie_obj.uid)

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
        f"\nWorker: {index}, cloud_acceptor: {cloud_acceptor_url[-20:]}, total: {len(success)}\n"
        f"{'-'*80}"
    )


async def listen_ws():
    async def on_message(message):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        now = int(time.time())

        raffle_type = data["raffle_type"]
        ts = data["ts"]
        room_id = data["real_room_id"]
        raffle_id = data["raffle_id"]
        gift_type = data.get("gift_type", "")
        gift_name = data.get("gift_name", "")

        if raffle_type == "tv":
            act = "join_tv_v5"
            time_wait = data["time_wait"]
            max_time = data["max_time"]
            accept_start_time = ts + time_wait
            accept_end_time = ts + max_time
            wait_time = int((accept_end_time - accept_start_time - 8) * random.random())
            recommended_implementation_time = accept_start_time + wait_time
            BatchLotteryNotice.add(room_id=room_id, gift_name=gift_name)
        elif raffle_type == "guard":
            act = "join_guard"
            recommended_implementation_time = ts + random.randint(60, 300)
        elif raffle_type == "pk":
            act = "join_pk"
            recommended_implementation_time = now
        else:
            return

        task_params = {
            "act": act,
            "room_id": room_id,
            "gift_id": raffle_id,
            "gift_type": gift_type,
            "gift_name": gift_name,
        }
        await DelayAcceptGiftsQueue.put(task_params, recommended_implementation_time)
        await redis_cache.set("LT_LAST_ACTIVE_TIME", value=int(time.time()))
        logging.info(
            f"RAFFLE received: {raffle_type} {room_id} $ {raffle_id}. "
            f"delay: {recommended_implementation_time - ts:.0f} -> {data}."
        )

    while True:
        session = aiohttp.ClientSession()
        async with session.ws_connect(url="wss://www.madliar.com/raffle_wss") as ws:
            logging.info(f"Ws Source Connected!")

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.ERROR:
                    break
                try:
                    await on_message(msg.data)
                except Exception as e:
                    logging.error(
                        f"Error in proc single: {e}\n"
                        f"`{msg.data}`\n"
                        f"{traceback.format_exc()}"
                    )

        logging.warning(f"Ws Connection broken!")


async def interval_assign_task(task_q):
    while True:
        task_params = await DelayAcceptGiftsQueue.get()
        for p in task_params:
            task_q.put_nowait(p)

        await asyncio.sleep(4)


async def main():
    logging.info("-" * 80)
    logging.info("LT ACCEPTOR started!")
    logging.info("-" * 80)

    task_q = asyncio.Queue()

    async def worker(index):
        while True:
            params = await task_q.get()
            start_time = time.time()
            try:
                await accept(index, **params)
            except Exception as e:
                logging.error(f"ACCEPTOR worker[{index}] error: {e}\n{traceback.format_exc()}")

            cost_time = time.time() - start_time
            if cost_time > 5:
                logging.warning(f"ACCEPTOR worker[{index}] exec long time: {cost_time:.3f}")

    await asyncio.gather(
        notice_qq(),
        listen_ws(),
        interval_assign_task(task_q),
        *[worker(index) for index in range(128)]
    )


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
