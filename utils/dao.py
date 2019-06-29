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

    async def delete(self, key):
        return await self.execute("DEL", key)

    async def ttl(self, key):
        return await self.execute("ttl", key)

    async def get(self, key):
        r = await self.execute("get", key)
        try:
            return pickle.loads(r)
        except TypeError:
            return None

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


redis_cache = RedisCache(**REDIS_CONFIG)


class CookieOperator(object):
    RAW_COOKIE_FILE = "data/cookies.txt"
    VALID_COOKIE_FILE = "data/valid_cookies.txt"
    VIP_COOKIE_FILE = "data/vip_cookies.txt"

    COOKIE_FILES = [
        RAW_COOKIE_FILE,
        VALID_COOKIE_FILE,
        VIP_COOKIE_FILE,
    ]

    WHITE_UID_LIST_FILE = "data/lt_white_uid_list.txt"

    @classmethod
    def delete_cookie_by_uid(cls, user_id):
        check_str = f"={user_id};"
        for file_name in cls.COOKIE_FILES:
            with open(file_name, "r") as f:
                cookies = [_.strip() for _ in f.readlines()]
                cookies = [_ for _ in cookies if _ and check_str not in _]

            with open(file_name, "w") as f:
                f.write("\n".join(cookies))

    @classmethod
    def add_uid_to_white_list(cls, user_id):
        user_id = int(user_id)

        with open(cls.WHITE_UID_LIST_FILE) as f:
            uid_list = [_.strip() for _ in f.readlines()]
            uid_list = {int(_) for _ in uid_list if _}

        if user_id in uid_list:
            return f"Already in! total: {len(uid_list)}"

        uid_list.add(user_id)
        with open(cls.WHITE_UID_LIST_FILE, "w") as f:
            f.write("\n".join([str(_) for _ in uid_list]))
        return f"OK. total: {len(uid_list)}"

    @classmethod
    def remove_uid_from_white_list(cls, user_id):
        user_id = int(user_id)

        with open(cls.WHITE_UID_LIST_FILE) as f:
            uid_list = [_.strip() for _ in f.readlines()]
            uid_list = {int(_) for _ in uid_list if _}

        if user_id not in uid_list:
            msg = f"Already removed! total: {len(uid_list)}"
        else:
            uid_list.remove(user_id)
            with open(cls.WHITE_UID_LIST_FILE, "w") as f:
                f.write("\n".join([str(_) for _ in uid_list]))
            msg = f"OK. total: {len(uid_list)}"

        cls.delete_cookie_by_uid(user_id)
        return msg

    @classmethod
    def get_cookie_by_uid(cls, user_id):
        if user_id == "DD":
            user_id = 20932326
        elif user_id == "LP":
            user_id = 39748080

        with open("data/valid_cookies.txt", "r") as f:
            cookies = f.readlines()

        if user_id == "*":
            return cookies[0].strip()

        for c in cookies:
            if f"={user_id};" in c:
                return c.strip()
        return ""


class BiliUserInfoCache(object):
    timeout = 3600 * 12

    __update_time = 0
    __cache_data = {}
    __cache_key = "BILI_LT_USER_ID_TO_NAME"

    @classmethod
    async def get_user_name_by_user_id(cls, uid):
        if cls.__update_time == 0 or time.time() - cls.__update_time > cls.timeout:
            cls.__cache_data = await redis_cache.hash_map_get(cls.__cache_key)
            cls.__update_time = time.time()
        return cls.__cache_data.get(uid)

    @classmethod
    async def set_user_name(cls, uid, name):
        return await redis_cache.hash_map_set(cls.__cache_key, key_values={uid: name})


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


class DanmakuMessageQ(object):
    _key = "DANMAKU_MQ_OF_CMD_"

    @classmethod
    async def put(cls, danmaku, *args, **kwargs):
        cmd = danmaku["cmd"]
        key = cls._key + cmd
        item = (danmaku, args, kwargs)
        return await redis_cache.list_push(key, item)

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
