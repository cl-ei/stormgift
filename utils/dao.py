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


redis_cache = GiftRedisCache(**REDIS_CONFIG)


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
