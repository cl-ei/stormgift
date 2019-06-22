import json
import pickle
import aioredis
from config import REDIS_CONFIG


class GiftRedisCache(object):
    def __init__(self, host, port, db, password):
        self.uri = f'redis://{host}:{port}'
        self.db = db
        self.password = password
        self.__redis_conn = None

    async def non_repeated_save(self, key, info, ex=3600*24*7):
        """

        :param key:
        :param info:
        :param ex:
        :return: True
        """
        if self.__redis_conn is None:
            self.__redis_conn = await aioredis.create_connection(
                address=self.uri, db=self.db, password=self.password
            )
        return await self.__redis_conn.execute("set", key, json.dumps(info), "ex", ex, "nx")

    async def set(self, key, value, timeout=0):
        v = pickle.dumps(value)
        if self.__redis_conn is None:
            self.__redis_conn = await aioredis.create_connection(
                address=self.uri, db=self.db, password=self.password
            )
        if timeout > 0:
            return await self.__redis_conn.execute("setex", key, timeout, v)
        else:
            return await self.__redis_conn.execute("set", key, v)

    async def ttl(self, key):
        if self.__redis_conn is None:
            self.__redis_conn = await aioredis.create_connection(
                address=self.uri, db=self.db, password=self.password
            )
        return await self.__redis_conn.execute("ttl", key)

    async def get(self, key):
        if self.__redis_conn is None:
            self.__redis_conn = await aioredis.create_connection(
                address=self.uri, db=self.db, password=self.password
            )
        r = await self.__redis_conn.execute("get", key)
        try:
            return pickle.loads(r)
        except TypeError:
            return None

    async def hash_map_set(self, name, key_values):
        if self.__redis_conn is None:
            self.__redis_conn = await aioredis.create_connection(
                address=self.uri, db=self.db, password=self.password
            )
        args = []
        for key, value in key_values.items():
            args.append(pickle.dumps(key))
            args.append(pickle.dumps(value))
        return await self.__redis_conn.execute("hmset", name, *args)

    async def hash_map_get(self, name, *keys):
        if self.__redis_conn is None:
            self.__redis_conn = await aioredis.create_connection(
                address=self.uri, db=self.db, password=self.password
            )

        if keys:
            r = await self.__redis_conn.execute("hmget", name, *[pickle.dumps(k) for k in keys])
            if not isinstance(r, list) or len(r) != len(keys):
                raise Exception(f"Redis hash map read error! r: {r}")

            result = {}
            for index in range(len(r)):
                result[keys[index]] = pickle.loads(r[index])
            return result

        else:
            """HDEL key field1 [field2] """
            r = await self.__redis_conn.execute("hgetall", name)
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


redis_cache = GiftRedisCache(**REDIS_CONFIG)


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
