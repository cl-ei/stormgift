import json
import aioredis


class GiftRedisCache(object):
    def __init__(self, host, port, db, password):
        self.uri = f'redis://{host}:{port}'
        self.db = db
        self.password = password
        self.__redis_conn = None

    async def non_repeated_save(self, key, info, ex=3600*24*7):
        if self.__redis_conn is None:
            self.__redis_conn = await aioredis.create_connection(
                address=self.uri, db=self.db, password=self.password
            )
        return await self.__redis_conn.execute("set", key, json.dumps(info), "ex", ex, "nx")
