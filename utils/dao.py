import time
import json
import random
import pickle
import asyncio
import aioredis
import datetime
from typing import List, Dict, Union, Any, Iterable, Tuple
from config import REDIS_CONFIG

PKL_PROTOCOL = pickle.DEFAULT_PROTOCOL  # 4


class RedisCache(object):
    def __init__(self, host, port, db, password):
        self.uri = f'redis://{host}:{port}'
        self.db = db
        self.password = password
        self.redis_conn = None

    async def execute(self, *args, **kwargs):
        if self.redis_conn is None:
            self.redis_conn = await aioredis.create_redis_pool(
                address=self.uri,
                db=self.db,
                password=self.password
            )
        return await self.redis_conn.execute(*args, **kwargs)

    async def close(self):
        if self.redis_conn is not None:
            self.redis_conn.close()
            await self.redis_conn.wait_closed()
            self.redis_conn = None

    @staticmethod
    def __dumps_py_obj(obj: Any) -> Union[bytes, bytearray]:
        return pickle.dumps(obj, protocol=PKL_PROTOCOL)

    @staticmethod
    def __loads_py_obj(content: Union[bytes, bytearray, str]) -> Any:
        if content is None:
            return None

        try:
            return pickle.loads(content)
        except pickle.UnpicklingError:
            return None

    async def keys(self, pattern) -> List[str]:
        keys = await self.execute("keys", pattern)
        return [k.decode("utf-8") for k in keys]

    async def set(
            self,
            key: str,
            value: Any,
            timeout: int = 0,
            _un_pickle: bool = False
    ) -> bool:
        v = value if _un_pickle else self.__dumps_py_obj(value)
        if timeout > 0:
            return await self.execute("setex", key, timeout, v)
        else:
            return await self.execute("set", key, v)

    async def expire(self, key: str, timeout: int) -> int:
        if timeout > 0:
            return await self.execute("EXPIRE", key, timeout)
        return 0

    async def set_if_not_exists(
            self,
            key: str,
            value: Any,
            timeout: int = 3600*24*7,
            _un_pickle: bool = False
    ):
        if not _un_pickle:
            value = self.__dumps_py_obj(value)
        return await self.execute("set", key, value, "ex", timeout, "nx")

    async def delete(self, key: str) -> int:
        return await self.execute("DEL", key)

    async def ttl(self, key: str) -> int:
        return await self.execute("ttl", key)

    async def get(self, key: str, _un_pickle: bool = False) -> Any:
        r = await self.execute("get", key)
        return r if _un_pickle else self.__loads_py_obj(r)

    async def mget(self, *keys: List[str], _un_pickle: bool = False) -> List[Any]:
        values = await self.execute("MGET", *keys)
        return values if _un_pickle else [self.__loads_py_obj(v) for v in values]

    async def hmset(self, key: str, field_value: dict, _un_pickle: bool = False) -> bool:
        """
        hash_map_set

        HMSET key field1 value1 [field2 value2 ]
        """
        args = []
        for field, value in field_value.items():
            if not _un_pickle:
                field = self.__dumps_py_obj(field)
                value = self.__dumps_py_obj(value)
            args.extend([field, value])
        return await self.execute("hmset", key, *args)

    async def hmget(self, key: str, *fields: List[Any], _un_pickle: bool = False) -> dict:
        """
        hash map get

        HMGET KEY_NAME FIELD1...FIELDN
        """
        if not _un_pickle:
            fields = [self.__dumps_py_obj(f) for f in fields]
        values = await self.execute("hmget", key, *fields)

        result = {}
        for i, field in enumerate(fields):
            value = values[i] if _un_pickle else self.__loads_py_obj(values[i])
            result[field] = value
        return result

    async def hgetall(self, key: str, _un_pickle: bool = False) -> dict:
        """
        hash map get all

        HGETALL KEY_NAME
        """
        r = await self.execute("hgetall", key)
        result = {}
        key_temp = None
        for index in range(len(r)):
            if index % 2 == 0:
                key_temp = r[index] if _un_pickle else self.__loads_py_obj(r[index])
            else:
                value = r[index] if _un_pickle else self.__loads_py_obj(r[index])
                result[key_temp] = value
        return result

    async def hash_map_multi_get(self, *keys) -> List[dict]:
        user_dict_list = await self.execute(
            "eval",
            "local rst={}; for i,v in pairs(KEYS) do rst[i]=redis.call('hgetall', v) end;return rst",
            len(keys),
            *keys
        )

        result = []
        for info in user_dict_list:
            temp_k = None
            user_dict = {}
            for i, field in enumerate(info):
                field = pickle.loads(field)
                if i % 2 == 0:
                    temp_k = field
                else:
                    user_dict[temp_k] = field
            result.append(user_dict)
        return result

    async def list_push(self, name, *items, _un_pickle: bool = False):
        if not _un_pickle:
            items = [self.__dumps_py_obj(e) for e in items]
        r = await self.execute("LPUSH", name, *items)
        return r

    async def list_rpop_to_another_lpush(self, source_list_name, dist_list_name):
        r = await self.execute("RPOPLPUSH", source_list_name, dist_list_name)
        if not r:
            return None
        return pickle.loads(r)

    async def list_del(self, name, item, _un_pickle: bool = False):
        if not _un_pickle:
            item = self.__dumps_py_obj(item)
        r = await self.execute("LREM", name, 0, item)
        return r

    async def list_get_all(self, name):
        r = await self.execute("LRANGE", name, 0, 100000)
        if isinstance(r, list):
            return [pickle.loads(e) for e in r]
        return []

    async def list_rpop(self, name):
        v = await self.execute("RPOP", name)
        if v is None:
            return None
        return pickle.loads(v)

    async def list_br_pop(self, *names, timeout=10):
        r = await self.execute("BRPOP", *names, "LISTN", timeout)
        if r is None:
            return None
        return r[0], pickle.loads(r[1])

    async def set_add(self, name, *items, _un_pickle: bool = False):
        if not _un_pickle:
            items = [self.__dumps_py_obj(e) for e in items]
        r = await self.execute("SADD", name, *items)
        return r

    async def set_remove(self, name, *items, _un_pickle: bool = False):
        if not _un_pickle:
            items = [self.__dumps_py_obj(e) for e in items]
        r = await self.execute("SREM", name, *items)
        return r

    async def set_is_member(self, name, item, _un_pickle: bool = False) -> bool:
        """ 判断 item 是否为 name: set 中的成员 """
        member = item if _un_pickle else self.__dumps_py_obj(item)
        return await self.execute("SISMEMBER", name, member)

    async def set_get_all(self, name):
        r = await self.execute("SMEMBERS", name)
        if isinstance(r, list):
            return [pickle.loads(e) for e in r]
        return []

    async def set_get_count(self, name):
        r = await self.execute("SCARD", name)
        return r

    async def incr(self, key):
        return await self.execute("INCR", key)

    async def sorted_set_zadd(self, key, *args):
        # args: score, member, ...
        safe_args = []
        if len(args) % 2 != 0:
            raise ValueError("Error args.")

        for i, arg in enumerate(args):
            if i % 2 == 1:
                safe_args.append(str(arg))
            else:
                safe_args.append(float(arg))
        return await self.execute("ZADD", key, *safe_args)

    async def sorted_set_zcard(self, key):
        return await self.execute("ZCARD", key)

    async def sorted_set_zincr(self, key, member, increment):
        return await self.execute("ZINCRBY", key, increment, member)

    async def sorted_set_zrange_by_score(self, key, min_="-inf", max_="+inf", with_scores=False, offset=0, limit=1000):
        args = ["ZRANGEBYSCORE", key, min_, max_]
        if with_scores:
            args.append("WITHSCORES")
        args.extend(["limit", offset, limit])
        r = await self.execute(*args)
        if not with_scores:
            return [_.decode() for _ in r]
        result = []
        for i, data in enumerate(r):
            if i % 2 == 0:
                result.append(data.decode("utf-8"))
            else:
                result.append(float(data))
        return result

    async def sorted_set_zrem(self, key, *members):
        return await self.execute("ZREM", key, *members)

    async def sorted_set_zrank(self, key, member, reversed=True):
        cmd = "ZREVRANK" if reversed else "ZRANK"
        return await self.execute(cmd, key, member)

    async def sorted_set_zrem_by_rank(self, key, start, stop):
        return await self.execute("ZREMRANGEBYRANK", key, start, stop)

    async def sorted_set_zrem_by_score(self, key, min_, max_):
        return await self.execute("ZREMRANGEBYSCORE", key, min_, max_)

    async def sorted_set_zscore(self, key, member):
        return await self.execute("ZSCORE", key, member)

    async def zset_zadd(self, key: str, member_pairs: Iterable[Tuple[Any, float]], _un_pickle=False):
        """
        向有序集合添加一个或多个成员，或者更新已存在成员的分数

        ZADD key score1 member1 [score2 member2]

        """
        safe_args = []
        for member, score in member_pairs:
            if not _un_pickle:
                member = self.__dumps_py_obj(member)
            safe_args.extend([float(score), member])
        return await self.execute("ZADD", key, *safe_args)

    async def zset_zcard(self, key) -> int:
        """ 获取有序集合的成员数 """
        return await self.execute("ZCARD", key)

    async def zset_zrange_by_score(
            self,
            key: str,
            min_: Union[str, float] = "-inf",
            max_: Union[str, float] = "+inf",
            offset: int = 0,
            limit: int = 10000,
            _un_pickle: bool = False,
    ) -> Iterable[Tuple[Any, float]]:
        """
        通过分数返回有序集合指定区间内的成员

        ZRANGEBYSCORE key min max [WITHSCORES] [LIMIT]
        """
        result = await self.execute(
            "ZRANGEBYSCORE", key, min_, max_, "WITHSCORES",
            "limit", offset, limit
        )

        return_data = []
        temp_obj = None
        for i, data in enumerate(result):
            if i % 2 == 0:  # member
                if not _un_pickle:
                    data = pickle.loads(data)
                temp_obj = data
            else:
                return_data.append((temp_obj, float(data)))
        return return_data

    async def zset_zrem(self, key, *members, _un_pickle=False):
        """
        移除有序集合中的一个或多个成员

        ZREM key member [member ...]
        """
        if not _un_pickle:
            members = [self.__dumps_py_obj(m) for m in members]
        return await self.execute("ZREM", key, *members)

    async def zset_zrem_by_score(
            self,
            key: str,
            min_: Union[str, float],
            max_: Union[str, float]
    ) -> int:
        """
        移除有序集合中给定的分数区间的所有成员

        ZREMRANGEBYSCORE key min max
        """
        return await self.execute("ZREMRANGEBYSCORE", key, min_, max_)

    async def zset_zscore(self, key: str, member: Any, _un_pickle: bool = False):
        """
        返回有序集中，成员的分数值

        ZSCORE key member
        """
        if not _un_pickle:
            member = self.__dumps_py_obj(member)
        return await self.execute("ZSCORE", key, member)


redis_cache = RedisCache(**REDIS_CONFIG)


class RedisLock:
    def __init__(self, key, timeout=30):
        self.key = f"LT_LOCK_{key}"
        self.timeout = timeout

    async def __aenter__(self):
        while True:
            lock = await redis_cache.set_if_not_exists(key=self.key, value=1, timeout=self.timeout)
            if lock:
                return self
            else:
                await asyncio.sleep(0.2 + random.random())

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await redis_cache.delete(self.key)


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


async def test():
    pass


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
