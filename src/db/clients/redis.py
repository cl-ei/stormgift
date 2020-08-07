import uuid
import pickle
import asyncio
import aioredis
from typing import *


class RedisClient:

    PICKLE_PROTOCOL = 4  # pickle.DEFAULT_PROTOCOL

    def __init__(self, conn: Union[aioredis.RedisConnection, aioredis.ConnectionsPool] = None):
        self.redis_conn = conn

    @property
    def conn(self):
        return self.redis_conn

    async def open_connection(self):
        from config import REDIS_CONFIG

        redis_uri = "redis://:{password}@{host}:{port}/{db}".format(**REDIS_CONFIG)
        self.redis_conn = await aioredis.create_redis_pool(address=redis_uri)

    async def close(self):
        if self.redis_conn is not None:
            self.redis_conn.close()
            await self.redis_conn.wait_closed()
            self.redis_conn = None

    @classmethod
    def _dumps(cls, obj: Any) -> Union[bytes, bytearray]:
        return pickle.dumps(obj, protocol=cls.PICKLE_PROTOCOL)

    @staticmethod
    def _loads(content: Union[str, bytes, bytearray]) -> Any:
        if content is None:
            return None
        try:
            return pickle.loads(content)
        except (TypeError, pickle.UnpicklingError) as e:
            # NOTE: add log
            raise e

    async def execute(self, *args, **kwargs) -> Any:
        if self.redis_conn is None:
            await self.open_connection()
        return await self.redis_conn.execute(*args, **kwargs)

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
        v = value if _un_pickle else self._dumps(value)
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
            value = self._dumps(value)
        return await self.execute("set", key, value, "ex", timeout, "nx")

    async def delete(self, key: str) -> int:
        return await self.execute("DEL", key)

    async def ttl(self, key: str) -> int:
        return await self.execute("ttl", key)

    async def get(self, key: str, _un_pickle: bool = False) -> Any:
        r = await self.execute("get", key)
        return r if _un_pickle else self._loads(r)

    async def mget(self, *keys: List[str], _un_pickle: bool = False) -> List[Any]:
        values = await self.execute("MGET", *keys)
        return values if _un_pickle else [self._loads(v) for v in values]

    async def hmset(self, key: str, field_value: dict, _un_pickle: bool = False) -> bool:
        """
        hash_map_set

        HMSET key field1 value1 [field2 value2 ]
        """
        args = []
        for field, value in field_value.items():
            if not _un_pickle:
                field = self._dumps(field)
                value = self._dumps(value)
            args.extend([field, value])
        return await self.execute("hmset", key, *args)

    async def hmget(self, key: str, *fields: List[Any], _un_pickle: bool = False) -> dict:
        """
        hash map get

        HMGET KEY_NAME FIELD1...FIELDN
        """
        if not _un_pickle:
            fields = [self._dumps(f) for f in fields]
        values = await self.execute("hmget", key, *fields)

        result = {}
        for i, field in enumerate(fields):
            value = values[i] if _un_pickle else self._loads(values[i])
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
                key_temp = r[index] if _un_pickle else self._loads(r[index])
            else:
                value = r[index] if _un_pickle else self._loads(r[index])
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
            items = [self._dumps(e) for e in items]
        r = await self.execute("LPUSH", name, *items)
        return r

    async def list_rpop_to_another_lpush(self, source_list_name, dist_list_name):
        r = await self.execute("RPOPLPUSH", source_list_name, dist_list_name)
        if not r:
            return None
        return pickle.loads(r)

    async def list_del(self, name, item, _un_pickle: bool = False):
        if not _un_pickle:
            item = self._dumps(item)
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
            items = [self._dumps(e) for e in items]
        r = await self.execute("SADD", name, *items)
        return r

    async def set_remove(self, name, *items, _un_pickle: bool = False):
        if not _un_pickle:
            items = [self._dumps(e) for e in items]
        r = await self.execute("SREM", name, *items)
        return r

    async def set_is_member(self, name, item, _un_pickle: bool = False) -> bool:
        """ 判断 item 是否为 name: set 中的成员 """
        member = item if _un_pickle else self._dumps(item)
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
                member = self._dumps(member)
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
            members = [self._dumps(m) for m in members]
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
            member = self._dumps(member)
        return await self.execute("ZSCORE", key, member)


class GlobalLock:
    """
    基于 Redis 构建的一个全局锁

    使用 Redis setnx 命令来加锁，在结束的时候会再判断
    一次锁是否是自己加的，若是，则释放。

    Parameters
    ----------
    redis: RedisClient

    name: str
        锁的名. 区分不能同时进行的操作的最小粒度的 key

    lock_time: int
        锁定的时间. 一般适用于很短就能完成的场景，长时间
        的任务不推荐使用这种办法，因为中途若发生譬如 worker
        重启等异常，则持有的锁在超时时间内不能开锁。

    try_times: int = 3
        尝试加锁的次数。若置为 0，则会反复加锁，直到获取到锁。
        0 值应当慎用，会产生大量 Redis 请求.

    _retry_interval: float, seconds
        在每次加锁失败后，休眠的时间，最小 0.1 秒

    Examples
    --------
    >>> name = f"task:137:clone"
    ... async with GlobalLock(redis=RedisClient(), name=name) as lock:
    ...     if not lock.locked:
    ...         raise RuntimeError(f"另一个人正在操作...")
    ...
    ...     # 在这里进行
    ...     # ...

    """
    key_prefix = "LOCK:"

    def __init__(
        self,
        redis: RedisClient,
        name: str,
        lock_time: int = 5,
        try_times: int = 3,
        _retry_interval: float = 0.1
    ):
        self.redis = redis
        self.key = f"{self.key_prefix}:{name}"
        self.lock_time = lock_time
        self.try_times = try_times
        self._retry_interval = max(0.1, _retry_interval)

        self.__locked: bool = False
        self.__identification: str = f"{uuid.uuid4()}"

    async def __aenter__(self):
        acquire_times = 0
        while True:
            lock_success = await self.redis.set_if_not_exists(
                key=self.key,
                value=self.__identification,
                timeout=self.lock_time,
                _un_pickle=True,
            )
            if lock_success:
                self.__locked = True
                return self

            if self.try_times > 0:
                acquire_times += 1
                if acquire_times >= self.try_times:
                    return self

            await asyncio.sleep(self._retry_interval)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self.__locked:
            return

        await self.redis.execute(
            "EVAL",
            (
                "if redis.call('get',KEYS[1]) == ARGV[1] then \n"
                "return redis.call('del',KEYS[1]) \n"
                "else \n"
                "return 0 \n"
                "end"
            ),
            1,  # 后续的参数中，key的个数，其余的为ARGS。LUA脚本中从下标从1开始
            self.key,
            self.__identification
        )
        self.__locked = False

    @property
    def locked(self) -> bool:
        return self.__locked
