import asyncio
import aiomysql
from config import MYSQL_CONFIG


class AsyncMySQL:

    @staticmethod
    async def execute(*args, **kwargs):
        conn = await aiomysql.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            db=MYSQL_CONFIG["database"],
            loop=asyncio.get_event_loop()
        )
        cursor = await conn.cursor()
        await cursor.execute(*args, **kwargs)
        r = await cursor.fetchall()

        await cursor.close()
        conn.close()

        return r
