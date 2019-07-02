import asyncio
import aiomysql
from config import MYSQL_CONFIG


class AsyncMySQL:

    conn = None

    @classmethod
    async def execute(cls, *args, **kwargs):
        if cls.conn is None:
            cls.conn = await aiomysql.connect(
                host=MYSQL_CONFIG["host"],
                port=MYSQL_CONFIG["port"],
                user=MYSQL_CONFIG["user"],
                password=MYSQL_CONFIG["password"],
                db=MYSQL_CONFIG["database"],
                loop=asyncio.get_event_loop()
            )
        cursor = await cls.conn.cursor()
        await cursor.execute(*args, **kwargs)
        r = await cursor.fetchall()
        await cursor.close()
        return r
