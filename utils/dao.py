import re
import time
import json
import random
import pickle
import asyncio
import aioredis
import datetime
from config import REDIS_CONFIG, REDIS_CONFIG_FOR_GO


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

    async def set(self, key, value, timeout=0, _un_pickle=False):
        v = value if _un_pickle else pickle.dumps(value)
        if timeout > 0:
            return await self.execute("setex", key, timeout, v)
        else:
            return await self.execute("set", key, v)

    async def expire(self, key, timeout):
        if timeout > 0:
            return await self.execute("EXPIRE", key, timeout)

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
        room_id = [int(r) for r in room_id if r not in (0, "", "0", None)]
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

    _go_redis_client = None

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
        live_room_id_set = {
            int(room_id) for room_id in live_room_id_set
            if room_id not in (0, "0", None, "")
        }

        if cls._go_redis_client is None:
            cls._go_redis_client = RedisCache(**REDIS_CONFIG_FOR_GO)

        go_value = "$".join([str(_) for _ in sorted(live_room_id_set)])
        key = "LT_MONITOR_LIVE_ROOMS"
        await cls._go_redis_client.set(key=key, value=go_value, _un_pickle=True)

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
    async def get_all(cls):
        keys = await redis_cache.keys(f"{cls.key}_*")
        settings = await redis_cache.mget(*keys)
        result = {}
        for i, key in enumerate(keys):
            setting = settings[i]
            user_id = int(key[len(cls.key) + 1:])

            for _ in [1, 2, 3]:
                madel_i = f"medal_{_}"
                if madel_i not in setting:
                    setting[madel_i] = ""
            result[user_id] = setting

        return result

    @classmethod
    async def get(cls, uid):
        key = f"{cls.key}_{uid}"
        settings = await redis_cache.get(key=key)
        if not isinstance(settings, dict):
            settings = {}

        for key in ("tv_percent", "guard_percent", "pk_percent"):
            if key not in settings:
                settings[key] = 100

        if "storm_percent" not in settings:
            settings["storm_percent"] = 0
        if "anchor_percent" not in settings:
            settings["anchor_percent"] = 0

        for i in [1, 2, 3]:
            key = f"medal_{i}"
            if key not in settings:
                settings[key] = ""

        return settings

    @classmethod
    async def set(
        cls,
        uid,
        tv_percent=100,
        guard_percent=100,
        pk_percent=100,
        storm_percent=0,
        anchor_percent=0,
        medal_1="",
        medal_2="",
        medal_3="",
    ):

        key = f"{cls.key}_{uid}"
        settings = await redis_cache.get(key=key)
        if not isinstance(settings, dict):
            settings = {}
        settings["tv_percent"] = tv_percent
        settings["guard_percent"] = guard_percent
        settings["pk_percent"] = pk_percent
        settings["storm_percent"] = storm_percent
        settings["anchor_percent"] = anchor_percent
        settings["medal_1"] = medal_1
        settings["medal_2"] = medal_2
        settings["medal_3"] = medal_3
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

            if key in ("storm_percent", "anchor_percent"):
                percent = setting.get(key, 0)
            else:
                percent = setting.get(key, 100)
            if random.randint(0, 99) < percent:  # 考虑到percent == 0时
                result.append(cookie)

        return result


class StormGiftBlackRoom:
    key = "LT_STORM_GIFT_BLOCKED"

    @classmethod
    async def set_blocked(cls, user_id):
        key = f"{cls.key}_{user_id}"
        await redis_cache.set(key=key, value=1, timeout=3600*3)

    @classmethod
    async def is_blocked(cls, user_id):
        key = f"{cls.key}_{user_id}"
        is_blocked = await redis_cache.get(key)
        return is_blocked == 1


class SuperDxjUserSettings:
    key = "LT_SUPER_DXJ_SETTINGS"

    @classmethod
    async def set(
            cls,
            room_id: int,
            account: str,
            password: str,
            carousel_msg: list,
            carousel_msg_interval: int,
            thank_silver: int,
            thank_silver_text: str,
            thank_gold: int,
            thank_gold_text: str,
            thank_follower: int,
            thank_follower_text: str,
            auto_response: list,
    ):
        key = f"{cls.key}_{room_id}"
        value = {
            "account": account,
            "password": password,
            "carousel_msg": carousel_msg,
            "carousel_msg_interval": carousel_msg_interval,
            "thank_silver": thank_silver,
            "thank_silver_text": thank_silver_text,
            "thank_gold": thank_gold,
            "thank_gold_text": thank_gold_text,
            "thank_follower": thank_follower,
            "thank_follower_text": thank_follower_text,
            "auto_response": auto_response,
            "last_update_time": int(time.time()),
        }
        await redis_cache.set(key=key, value=value)

    @classmethod
    async def get(cls, room_id):
        key = f"{cls.key}_{room_id}"
        r = await redis_cache.get(key)
        if not isinstance(r, dict):
            r = {}

        r.setdefault("account", "")
        r.setdefault("password", "")
        r.setdefault("carousel_msg", [])
        r.setdefault("carousel_msg_interval", 120)

        default_thank_text = "感谢{user}赠送的{num}个{gift},大气大气~"
        r.setdefault("thank_silver", 0)
        r.setdefault("thank_silver_text", default_thank_text)
        r.setdefault("thank_gold", 0)
        r.setdefault("thank_gold_text", default_thank_text)
        r.setdefault("thank_follower", 0)

        default_thank_text = "感谢{user}的关注~"
        r.setdefault("thank_follower_text", default_thank_text)
        r.setdefault("auto_response", [])
        r.setdefault("last_update_time", int(time.time())),

        auto_response = []
        for pair in r["auto_response"]:
            if pair and len(pair) == 2 and pair[0] and pair[1]:
                auto_response.append(pair)
        r["auto_response"] = auto_response

        return r


class SuperDxjUserAccounts:
    key = "LT_SUPER_DXJ_ACCOUNT"

    @classmethod
    async def get(cls, user_id):
        key = f"{cls.key}_{user_id}"
        return await redis_cache.get(key=key)

    @classmethod
    async def set(cls, user_id, password):
        key = f"{cls.key}_{user_id}"
        return await redis_cache.set(key=key, value=password)

    @classmethod
    async def delete(cls, user_id):
        key = f"{cls.key}_{user_id}"
        return await redis_cache.delete(key=key)

    @classmethod
    async def get_all_live_rooms(cls):
        p = f"{cls.key}_*"
        r = await redis_cache.keys(p)

        result = []
        for k in r:
            try:
                room_id = k[len(cls.key) + 1:]
                result.append(int(room_id))
            except (ValueError, TypeError):
                continue

        return result


class SuperDxjCookieMgr:
    key_prefix = f"LT_SUPER_DXJ_USER_COOKIE"

    @classmethod
    async def save_cookie(cls, account, cookie):
        key = f"{cls.key_prefix}_{account}"
        await redis_cache.set(key, cookie, timeout=3600*24*30)

    @classmethod
    async def load_cookie(cls, account):
        key = f"{cls.key_prefix}_{account}"
        return await redis_cache.get(key)

    @classmethod
    async def set_invalid(cls, account):
        key = f"{cls.key_prefix}_{account}"
        await redis_cache.delete(key)


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
        if r:
            score = await redis_cache.sorted_set_zscore(key=key, member=r[-1])
        else:
            score = 0
        return float(score), r

    @classmethod
    async def get_count(cls, user_id):
        key = f"{cls.key}_{user_id}"
        return await redis_cache.sorted_set_zcard(key)


class DelayAcceptGiftsMQ:
    key = "LT_DELAY_ACCEPT"

    @classmethod
    async def put(cls, gift_key, accept_time):
        await redis_cache.sorted_set_zadd(cls.key, accept_time, gift_key)

    @classmethod
    async def get(cls):
        now = time.time()
        r = await redis_cache.sorted_set_zrange_by_score(key=cls.key, max_=now)
        if r:
            await redis_cache.sorted_set_zrem(cls.key, *r)
        return r


async def test():
    # now = time.time() + 10
    # r = await DelayAcceptGiftsMQ.put("T1234", now)
    # print(r)

    s = await DelayAcceptGiftsMQ.get()
    print(s)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
