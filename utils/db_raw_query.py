import asyncio
import aiomysql
from config import MYSQL_CONFIG


class AsyncMySQL:
    __conn = None

    @classmethod
    async def execute(cls, *args, _commit=False, **kwargs):
        if cls.__conn is None:
            cls.__conn = await aiomysql.connect(
                host=MYSQL_CONFIG["host"],
                port=MYSQL_CONFIG["port"],
                user=MYSQL_CONFIG["user"],
                password=MYSQL_CONFIG["password"],
                db=MYSQL_CONFIG["database"],
                loop=asyncio.get_event_loop()
            )
        cursor = await cls.__conn.cursor()
        await cursor.execute(*args, **kwargs)
        if _commit:
            await cls.__conn.commit()
        r = await cursor.fetchall()
        await cursor.close()
        # conn.close()
        return r
