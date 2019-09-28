import re
import time
import json
import random
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

    async def keys(self, pattern):
        keys = await self.execute("keys", pattern)
        return [k.decode("utf-8") for k in keys]

    async def set(self, key, value, timeout=0):
        v = pickle.dumps(value)
        if timeout > 0:
            return await self.execute("setex", key, timeout, v)
        else:
            return await self.execute("set", key, v)

    async def expire(self, key, timeout):
        if timeout > 0:
            return await self.execute("	EXPIRE", key, timeout)

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

    async def mget(self, *keys, _un_pickle=False):
        r = await self.execute("MGET", *keys)

        if _un_pickle:
            return r

        result = []
        for _ in r:
            try:
                _ = pickle.loads(_)
            except (TypeError, pickle.UnpicklingError):
                _ = TypeError("UnpicklingError")
            result.append(_)
        return result

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

    async def list_rpop_to_another_lpush(self, source_list_name, dist_list_name):
        r = await self.execute("RPOPLPUSH", source_list_name, dist_list_name)
        if not r:
            return None
        return pickle.loads(r)

    async def list_del(self, name, item):
        r = await self.execute("LREM", name, 0, pickle.dumps(item))
        return r

    async def list_get_all(self, name):
        # count = await self.execute("LLEN", name)

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


class LtUserLoginPeriodOfValidity(object):
    _key = "LT_USER_LOGIN_PERIOD_"

    @classmethod
    async def update(cls, user_id, timeout=3600*24*40):
        key = cls._key + str(user_id)
        return await redis_cache.set(key=key, value="IN_PERIOD", timeout=timeout)

    @classmethod
    async def in_period(cls, user_id):
        key = cls._key + str(user_id)
        r = await redis_cache.get(key=key)
        return r == "IN_PERIOD"


class RaffleToCQPushList(object):
    _key = "RAFFLE_TO_CQ_"

    @classmethod
    async def add(cls, bili_uid, qq_uid):
        key = cls._key + str(bili_uid)
        value = qq_uid
        return await redis_cache.set(key, value)

    @classmethod
    async def get(cls, bili_uid):
        key = cls._key + str(bili_uid)
        return await redis_cache.get(key)

    @classmethod
    async def get_all(cls, return_raw_keys=False):
        key = cls._key + "*"
        keys = await redis_cache.execute("keys", key)
        if return_raw_keys or not keys:
            return keys

        qq_uid_list = await redis_cache.mget(*keys)
        result = []
        index = 0
        for qq_uid in qq_uid_list:
            bili_uid = int(keys[index][len(cls._key):])
            result.append((bili_uid, qq_uid))
            index += 1
        return result

    @classmethod
    async def del_by_bili_uid(cls, bili_uid):
        key = cls._key + str(bili_uid)
        return await redis_cache.delete(key)

    @classmethod
    async def del_by_qq_uid(cls, qq_uid):
        keys = await cls.get_all(return_raw_keys=True)
        if keys:
            qq_uids = await redis_cache.mget(*keys)
            index = 0
            for _ in qq_uids:
                if _ == qq_uid:
                    return await redis_cache.delete(keys[index])
                index += 1
        return 0


class BiliToQQBindInfo(object):
    key = "BINDINFO_BILI_TO_QQ"

    @classmethod
    async def bind(cls, qq, bili):
        r = await redis_cache.get(cls.key)

        if not isinstance(r, (list, tuple)):
            r = []
        r = [_ for _ in r if _[0] != qq]
        r.append((qq, bili))

        return await redis_cache.set(key=cls.key, value=r)

    @classmethod
    async def get_by_qq(cls, qq):
        r = await redis_cache.get(cls.key)
        for qq_num, bili in r:
            if qq_num == qq:
                return int(bili)
        return None

    @classmethod
    async def get_by_bili(cls, bili):
        r = await redis_cache.get(cls.key)
        for qq, b in r:
            if b == bili:
                return qq
        return None


class HansyDynamicNotic(object):
    key = "HANSY_DYNAMIC_NOTICE"

    @classmethod
    async def add(cls, qq):
        await redis_cache.set_add(cls.key, qq)

    @classmethod
    async def remove(cls, qq):
        await redis_cache.set_remove(cls.key, qq)

    @classmethod
    async def get(cls):
        return await redis_cache.set_get_all(cls.key)


class HYMCookies:
    key = "HYM_COOKIES_"

    @classmethod
    async def add(cls, account, password, cookie):
        key = cls.key + str(account)
        value = {"cookie": cookie, "password": password}
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


class HYMCookiesOfCl:
    key = "HYM_CL_COOKIES_"

    @classmethod
    async def add(cls, account, password, cookie):
        key = cls.key + str(account)
        value = {"cookie": cookie, "password": password}
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


class LTUserSettings:
    key = f"LT_USER_SETTINGS"

    @classmethod
    async def get(cls, uid):
        key = f"{cls.key}_{uid}"
        settings = await redis_cache.get(key=key)
        if not isinstance(settings, dict):
            settings = {
                "tv_percent": 100,
                "guard_percent": 100,
                "pk_percent": 100,
            }
        return settings

    @classmethod
    async def set(cls, uid, tv_percent=100, guard_percent=100, pk_percent=100):
        key = f"{cls.key}_{uid}"
        settings = await redis_cache.get(key=key)
        if not isinstance(settings, dict):
            settings = {}
        settings["tv_percent"] = tv_percent
        settings["guard_percent"] = guard_percent
        settings["pk_percent"] = pk_percent
        await redis_cache.set(key=key, value=settings)
        return True

    @classmethod
    async def filter_cookie(cls, cookies, key):
        uid_list = [c.uid for c in cookies]
        keys = [f"{cls.key}_{u}" for u in uid_list]
        settings_list = await redis_cache.mget(*keys)

        result = []
        for index in range(len(cookies)):
            cookie = cookies[index]
            setting = settings_list[index]
            if not isinstance(setting, dict):
                setting = {}

            percent = setting.get(key, 100)
            if random.randint(0, 99) < percent:  # 考虑到percent == 0时
                result.append(cookie)

        return result


class UserRaffleRecordBasedOnRedis:
    user_raffle_record_key = "LT_USER_RAFFLE_CNT"

    @classmethod
    async def record(cls, user_id, gift_name, raffle_id, intimacy=0):
        user_raffle_record_key = (
            f"{cls.user_raffle_record_key}_{user_id}_"
            f"{datetime.datetime.now().date()}_{gift_name}_{intimacy}"
        )
        await redis_cache.incr(user_raffle_record_key)
        await redis_cache.expire(user_raffle_record_key, timeout=3600*72)

    @classmethod
    async def get_24(cls, user_id):
        pass


async def test():
    r = await UserRaffleRecordBasedOnRedis.get_24(20932326)
    print(r)

    pass


if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
