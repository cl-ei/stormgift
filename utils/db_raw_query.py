import asyncio
import aiomysql
from config import MYSQL_CONFIG


class AsyncMySQL:

    @classmethod
    async def execute(cls, *args, _commit=False, **kwargs):
        conn = await aiomysql.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            db=MYSQL_CONFIG["database"],
            loop=asyncio.get_event_loop()
        )

        async with conn.cursor() as cursor:
            await cursor.execute(*args, **kwargs)
            if _commit:
                await conn.commit()
            r = await cursor.fetchall()
        conn.close()
        return r
