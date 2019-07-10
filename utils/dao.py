import re
import time
import json
import pickle
import aioredis
import datetime
from config import REDIS_CONFIG


class RedisCache(object):
    def __init__(self, host, port, db, password):
        self.uri = f'redis://{host}:{port}'
        self.db = db
        self.password = password
        self.redis_conn = None

    async def execute(self, *args, **kwargs):
        if self.redis_conn is None:
            self.redis_conn = await aioredis.create_pool(
                address=self.uri,
                db=self.db,
                password=self.password
            )
        return await self.redis_conn.execute(*args, **kwargs)

    async def non_repeated_save(self, key, info, ex=3600*24*7):
        return await self.execute("set", key, json.dumps(info), "ex", ex, "nx")

    async def set(self, key, value, timeout=0):
        v = pickle.dumps(value)
        if timeout > 0:
            return await self.execute("setex", key, timeout, v)
        else:
            return await self.execute("set", key, v)

    async def set_if_not_exists(self, key, value, timeout=3600*24*7):
        v = pickle.dumps(value)
        return await self.execute("set", key, v, "ex", timeout, "nx")

    async def delete(self, key):
        return await self.execute("DEL", key)

    async def ttl(self, key):
        return await self.execute("ttl", key)

    async def get(self, key):
        r = await self.execute("get", key)
        try:
            return pickle.loads(r)
        except (TypeError, pickle.UnpicklingError):
            return r

    async def hash_map_set(self, name, key_values):
        args = []
        for key, value in key_values.items():
            args.append(pickle.dumps(key))
            args.append(pickle.dumps(value))
        return await self.execute("hmset", name, *args)

    async def hash_map_get(self, name, *keys):
        if keys:
            r = await self.execute("hmget", name, *[pickle.dumps(k) for k in keys])
            if not isinstance(r, list) or len(r) != len(keys):
                raise Exception(f"Redis hash map read error! r: {r}")

            result = [pickle.loads(_) for _ in r]
            return result[0] if len(result) == 1 else result

        else:
            """HDEL key field1 [field2] """
            r = await self.execute("hgetall", name)
            if not isinstance(r, list):
                raise Exception(f"Redis hash map read error! r: {r}")

            result = {}
            key_temp = None
            for index in range(len(r)):
                if index & 1:
                    result[pickle.loads(key_temp)] = pickle.loads(r[index])
                else:
                    key_temp = r[index]
            return result

    async def list_push(self, name, *items):
        r = await self.execute("LPUSH", name, *[pickle.dumps(e) for e in items])
        return r

    async def list_del(self, name, item):
        r = await self.execute("LREM", name, 0, pickle.dumps(item))
        return r

    async def list_get_all(self, name):
        # count = await self.execute("LLEN", name)

        r = await self.execute("LRANGE", name, 0, 100000)
        if isinstance(r, list):
            return [pickle.loads(e) for e in r]
        return []

    async def list_br_pop(self, *names, timeout=10):
        r = await self.execute("BRPOP", *names, "LISTN", timeout)
        if r is None:
            return None
        return r[0], pickle.loads(r[1])

    async def set_add(self, name, *items):
        r = await self.execute("SADD", name, *[pickle.dumps(e) for e in items])
        return r

    async def set_remove(self, name, *items):
        r = await self.execute("SREM", name, *[pickle.dumps(e) for e in items])
        return r

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


redis_cache = RedisCache(**REDIS_CONFIG)


class HansyGiftRecords(object):
    gift_key = "HANSY_GIFT_{year}_{month}"

    @classmethod
    async def add_log(cls, uid, uname, gift_name, coin_type, price, count, created_timestamp, rnd=0):
        today = datetime.datetime.today()
        key = cls.gift_key.replace("{year}", str(today.year)).replace("{month}", str(today.month))
        r = await redis_cache.list_push(key, [uid, uname, gift_name, coin_type, price, count, created_timestamp, rnd])
        return r

    @classmethod
    async def get_log(cls):
        today = datetime.datetime.today()
        key = cls.gift_key.replace("{year}", str(today.year)).replace("{month}", str(today.month))
        r = await redis_cache.list_get_all(key)
        return r


class HansyQQGroupUserInfo(object):

    _key = "HANSY_QQ_GROUP_USER_INFO_{group_id}_{user_id}"

    @classmethod
    async def get_info(cls, group_id, user_id):
        key = cls._key.replace("{group_id}", str(group_id)).replace("{user_id}", str(user_id))
        r = await redis_cache.list_get_all(key)
        return r

    @classmethod
    async def add_info(cls, group_id, user_id, info):
        key = cls._key.replace("{group_id}", str(group_id)).replace("{user_id}", str(user_id))
        r = await redis_cache.list_push(key, info)
        return r

    @classmethod
    async def get_all_user_id(cls, group_id):
        key = cls._key.replace("{group_id}", str(group_id)).replace("{user_id}", "*")
        keys = await redis_cache.execute("KEYS", key)
        return [int(k.decode("utf-8").split("_")[-1]) for k in keys]


class ValuableLiveRoom(object):
    _key = "VALUABLE_LIVE_ROOM"

    @classmethod
    async def add(cls, *room_id):
        if not room_id:
            return 0

        r = await redis_cache.set_add(cls._key, *room_id)
        return r

    @classmethod
    async def get_all(cls):
        r = await redis_cache.set_get_all(cls._key)
        return r

    @classmethod
    async def get_count(cls):
        r = await redis_cache.set_get_count(cls._key)
        return r

    @classmethod
    async def delete(cls, *room_id):
        if not room_id:
            return 0

        r = await redis_cache.set_remove(cls._key, *room_id)
        return r


class InLotteryLiveRooms(object):
    _key = "IN_LOTTERY_LIVE_ROOM"
    time_out = 60*10

    @classmethod
    async def add(cls, room_id):
        old = await redis_cache.get(cls._key)
        if not isinstance(old, dict):
            old = dict()

        old[room_id] = time.time()
        return await redis_cache.set(cls._key, old)

    @classmethod
    async def get_all(cls):
        room_dict = await redis_cache.get(cls._key)
        if not isinstance(room_dict, dict):
            return set()

        result = {}
        now = time.time()
        changed = False
        for room_id, timestamp in room_dict.items():
            if now - timestamp < cls.time_out:
                result[room_id] = timestamp
            else:
                changed = True

        if changed:
            await redis_cache.set(cls._key, result)

        return set(result.keys())


class DanmakuMessageQ(object):
    _key = "DANMAKU_MQ_OF_CMD_"

    @classmethod
    async def put(cls, message):
        """
        message 必须是 tuple，第一个是DANMAKU的 python dict.

        :param message:
        :return:
        """
        danmaku = message[0]
        cmd = danmaku["cmd"]
        key = cls._key + cmd
        return await redis_cache.list_push(key, message)

    @classmethod
    async def get(cls, *cmds, timeout):
        keys = [cls._key + cmd for cmd in cmds]
        r = await redis_cache.list_br_pop(*keys, timeout=timeout)
        if r is None:
            return None
        return r[1]


class RaffleMessageQ(object):
    _key = "RAFFLE_MESSAGE"

    @classmethod
    async def put(cls, item):
        return await redis_cache.list_push(cls._key, item)

    @classmethod
    async def get(cls, timeout):
        r = await redis_cache.list_br_pop(cls._key, timeout=timeout)
        if r is None:
            return None
        return r[1]


class MonitorLiveRooms(object):
    """

    返回值是set 类型！

    """
    _key = "MonitorLiveRooms_KEY"
    _version_key = "MonitorLiveRooms_VERSION"
    __version_of_last_get = None
    __data_of_last_get = None

    @classmethod
    async def get(cls):
        version = await redis_cache.get(cls._version_key)
        if version == cls.__version_of_last_get:
            return cls.__data_of_last_get

        r = await redis_cache.get(cls._key)
        if not r or not isinstance(r, set):
            return set()

        cls.__version_of_last_get = version
        cls.__data_of_last_get = r

        return r

    @classmethod
    async def set(cls, live_room_id_set):
        if not isinstance(live_room_id_set, set):
            live_room_id_set = set(live_room_id_set)
        r = await redis_cache.set(cls._key, live_room_id_set)
        r2 = await redis_cache.set(cls._version_key, str(time.time()))
        return r, r2


class MonitorCommands(object):
    _key = "MonitorCommands"

    @classmethod
    async def get(cls):
        r = await redis_cache.get(cls._key)
        return r if isinstance(r, (list, tuple, set)) else []

    @classmethod
    async def set(cls, *cmds):
        r = await redis_cache.set(cls._key, [c for c in cmds if isinstance(c, str)])
        return r


async def test():
    key = "test"
    value = None

    r = await redis_cache.set(key, value)
    print(r)

    r = await redis_cache.ttl(key)
    print(r)

    r = await redis_cache.get(key)
    print(r)

    r = await redis_cache.get("abc")
    print(r)

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
