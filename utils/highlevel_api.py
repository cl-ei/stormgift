import time
import json
import random
import asyncio
import aiohttp
import datetime

from config import cloud_get_uid
from config.log4 import bili_api_logger as logging
from utils.dao import redis_cache


BLOCK_FRESH_TIME = 1


class ReqFreLimitApi(object):
    __req_time = {}

    @classmethod
    async def _wait(cls, f, wait_time):
        last_req_time = cls.__req_time.get(f)
        if last_req_time is None:
            cls.__req_time[f] = time.time()
        else:
            interval = time.time() - last_req_time
            if interval < wait_time:
                sleep_time = wait_time - interval
                logging.warn(f"High level api request frequency control: f: {f}, sleep_time: {sleep_time:.3f}")
                await asyncio.sleep(sleep_time)
            cls.__req_time[f] = time.time()

    @classmethod
    async def _update_time(cls, f):
        cls.__req_time[f] = time.time()

    @classmethod
    async def get_uid_by_name(cls, user_name, wait_time=2):
        cookie = await cls.get_available_cookie()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(cloud_get_uid, json={"cookie": cookie, "name": user_name}) as resp:
                    status_code = resp.status
                    content = await resp.text()
        except Exception as e:
            status_code = 5000
            content = f"Error: {e}"

        if status_code != 200:
            logging.error(f"Error happened when get_uid_by_name({user_name}), content: {content}.")
            return None

        try:
            r = json.loads(content)
            assert len(r) == 2
        except (json.JSONDecodeError, AssertionError) as e:
            logging.error(f"Error happened when get_uid_by_name({user_name}), e: {e}, content: {content}")
            return None

        flag, result = r
        if not flag:
            logging.error(f"Cannot get_uid_by_name by cloud_func, name: {user_name}, reason: {result}")
            return None
        return result

    @classmethod
    async def get_raffle_record(cls, uid):
        url = f"https://www.madliar.com/bili/raffles?day_range=7&json=1&user={uid}"
        async with aiohttp.request("get", url=url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            response = await resp.json()

        if response.get("code") != 0:
            return []

        raffle_data = response.get("raffle_data") or []
        user_name = response.get("user_name") or "??"
        results = []
        for r in raffle_data:
            results.append([
                user_name,
                r["display_room_id"],
                r["prize_gift_name"],
                datetime.datetime.strptime(r["expire_time"], "%Y-%m-%d %H:%M:%S"),  # 2020-01-30 13:25:43
            ])
        return results

    @classmethod
    async def get_guard_record(cls, uid):

        """
        user_obj = await AsyncMySQL.execute("select u.id, u.name from biliuser u where u.uid = %s", (uid, ))
        if not user_obj:
            return f"未能查询到用户?(uid: {uid})"

        user_obj_id, user_name = user_obj[0]

        guards = await AsyncMySQL.execute(
            "select g.room_id, g.gift_name, g.created_time "
            "from guard g "
            "where g.sender_obj_id = %s and g.created_time >= %s "
            "order by g.room_id, g.created_time desc;",
            (user_obj_id, datetime.datetime.now() - datetime.timedelta(days=45))
        )
        if not guards:
            return f"{user_name}(uid: {uid})在45天内没有开通过1条船。"

        rooms_info = await AsyncMySQL.execute(
            "select real_room_id, short_room_id, name from biliuser where real_room_id in %s;",
            ([r[0] for r in guards],)
        )
        room_id_map = {r[0]: r[1] for r in rooms_info if r[0] and r[1]}
        room_id_to_name = {r[0]: r[2] for r in rooms_info}

        def gen_time_prompt(interval):
            if interval > 3600*24:
                return f"约{int(interval // (3600*24))}天前"
            elif interval > 3600:
                return f"约{int(interval // 3600)}小时前"
            elif interval > 60:
                return f"约{int(interval // 60)}分钟前"
            return f"{int(interval)}秒前"

        now = datetime.datetime.now()
        info_map = {}
        for i, r in enumerate(guards):
            room_id, gift_name, created_time = r
            time_interval = (now - created_time).total_seconds()
            interval_prompt = gen_time_prompt(time_interval)
            prompt = f"　　　{interval_prompt}开通{gift_name}"

            if room_id not in info_map:
                info_map[room_id] = []
            for g in info_map[room_id]:
                if g[0] == prompt:
                    g[1] += 1
                    break
            else:
                info_map[room_id].append([prompt, 1])

        prompt = []
        info_list = [
            (room_id_map.get(room_id, room_id), room_id_to_name.get(room_id, "??"), r)
            for room_id, r in info_map.items()
        ]
        info_list.sort(key=lambda x: x[0])
        for short_room_id, name, r in info_list:
            prompt.append(f"{short_room_id}直播间(主播: {name})：")
            for p, num in r:
                prompt.append(f"{p}*{num}")
        prompt = f"\n".join(prompt)
        return f"{user_name}(uid: {uid})在45天内开通了{len(guards)}条船：\n\n{prompt}"
        """
        return f"功能维护中"

    @classmethod
    async def get_available_cookie(cls):
        key = "LT_AVAILABLE_COOKIES"
        r = await redis_cache.get(key)
        if r and isinstance(r, list):
            return random.choice(r)
        return ""
