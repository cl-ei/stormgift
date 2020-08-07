import time
import json
import datetime
from typing import List, Dict
from src.db.clients.redis import RedisClient


redis_cache = RedisClient()


class HYMCookies:
    key = "HYM_COOKIES_"

    @classmethod
    async def add(cls, account, password, cookie, access_token=None, refresh_token=None):
        key = cls.key + str(account)
        value = {"cookie": cookie, "password": password}
        if access_token and refresh_token:
            value.update({"access_token": access_token, "refresh_token": refresh_token})
        await redis_cache.set(key=key, value=value)

    @classmethod
    async def get(cls, account=None, return_dict=False):
        if account is None:
            keys = await redis_cache.keys(cls.key + "*")
            r = await redis_cache.mget(*keys)
            if not return_dict:
                return r

            result = {}
            for index in range(len(keys)):
                key = keys[index]
                account = key[len(cls.key):]
                data = r[index]
                result[account] = data
            return result

        r = await redis_cache.get(cls.key + str(account))
        return {account: r} if return_dict else r

    @classmethod
    async def set_invalid(cls, account):
        key = cls.key + str(account)
        data = await redis_cache.get(key)
        data["invalid"] = True
        await redis_cache.set(key, data)
        return True

    @classmethod
    async def set_blocked(cls, account):
        key = cls.key + str(account)
        data = await redis_cache.get(key)
        data["blocked"] = int(time.time())
        await redis_cache.set(key, data)
        return True


class HYMCookiesOfCl(HYMCookies):
    key = "HYM_CL_COOKIES_"


class UserRaffleRecord:
    key = "LT_USER_RAFFLE_RECORD"

    @classmethod
    async def create(cls, user_id, gift_name, raffle_id, intimacy=0, created_time=None):
        key = f"{cls.key}_{user_id}"
        if created_time is None:
            created_time = time.time()
        await redis_cache.sorted_set_zadd(key, created_time, f"{gift_name}${raffle_id}${intimacy}")
        await redis_cache.sorted_set_zrem_by_score(key=key, min_="-inf", max_=time.time() - 25*3600)

    @classmethod
    async def get_by_user_id(cls, user_id):  # -> list(float, list)
        key = f"{cls.key}_{user_id}"
        r = await redis_cache.sorted_set_zrange_by_score(
            key,
            min_=time.time() - 24*3600,
            max_="+inf",
            with_scores=False,
            offset=0, limit=50000
        )
        return r

    @classmethod
    async def get_count(cls, user_id):
        key = f"{cls.key}_{user_id}"
        return await redis_cache.sorted_set_zcard(key)


class DelayAcceptGiftsQueue:
    key = "LT_DELAY_ACCEPT"

    @classmethod
    async def put(cls, data, accept_time):
        data = json.dumps(data)
        await redis_cache.sorted_set_zadd(cls.key, accept_time, data)

    @classmethod
    async def get(cls):
        now = time.time()
        r = await redis_cache.sorted_set_zrange_by_score(key=cls.key, max_=now)
        if r:
            await redis_cache.sorted_set_zrem(cls.key, *r)
        result = []
        for d in r:
            try:
                result.append(json.loads(d))
            except (json.JSONDecodeError, TypeError):
                continue
        return result

    @classmethod
    async def get_all(cls):
        r = await redis_cache.sorted_set_zrange_by_score(key=cls.key, with_scores=True)
        result = []
        for i, d in enumerate(r):
            if i % 2 == 0:
                try:
                    d = json.loads(d)
                except (json.JSONDecodeError, TypeError):
                    pass
                result.append(d)
            else:
                result.append(d)
        return result


class MedalManager:
    key_prefix = "LT:INTI"
    today_key_prefix = "LT:INTI_TODAY"

    def __init__(self, room_id: int):
        self.room_id = room_id
        self.key = f"{self.key_prefix}:{room_id}"
        self.today_key = f"{self.today_key_prefix}:{room_id}"

    async def set_level_info(self, uid: int, level: int) -> int:
        return await redis_cache.hmset(self.key, {uid: level})

    async def get_level_info(self, *uids: int) -> Dict[int, dict]:
        return await redis_cache.hmget(self.key, *uids)

    async def get_today_prompted(self) -> List[int]:
        return await redis_cache.list_get_all(self.today_key)

    async def add_today_prompted(self, uid: int) -> None:
        await redis_cache.list_push(self.today_key, uid)


class SignManager:
    def __init__(self, room_id: int, user_id: int):
        self.room_id = room_id
        self.user_id = user_id
        self.key = F"LT_SIGN_V2_{room_id}"

    async def sign_dd(self):
        base = datetime.date.fromisoformat("2020-01-01")
        now = datetime.datetime.now().date()
        today_num = (now - base).days

        info = await redis_cache.get(key=self.key)
        info = info or []

        # 检查今日已有几人签到
        today_sign_count = 0
        for s in info:
            if today_num in s["sign"]:
                today_sign_count += 1
        dec_score = 0.001 * int(today_sign_count)

        for s in info:
            if s["id"] == self.user_id:
                if today_num in s["sign"]:
                    sign_success = False
                else:
                    s["sign"].insert(0, today_num)
                    sign_success = True

                continue_days = 0
                for delta in range(len(s["sign"])):
                    if (today_num - delta) in s["sign"]:
                        continue_days += 1
                    else:
                        break
                total_days = len(s["sign"])

                if sign_success:
                    s["score"] += 50 + min(84, 12 * (continue_days - 1)) - dec_score
                current_score = s["score"]
                break
        else:
            # 新用户
            s = {
                "id": self.user_id,
                "score": 50 - dec_score,
                "sign": [today_num],
            }
            info.append(s)
            continue_days = 1
            total_days = 1
            current_score = s["score"]
            sign_success = True

        await redis_cache.set(key=self.key, value=info)
        all_scores = sorted([s["score"] for s in info], reverse=True)
        rank = all_scores.index(current_score)
        return sign_success, continue_days, total_days, rank + 1, current_score, today_sign_count

    async def get_score(self):
        info = await redis_cache.get(self.key)
        info = info or []
        for s in info:
            if s["id"] == self.user_id:
                return s["score"]
        return 0
