import asyncio
import aiomysql
from config import MYSQL_CONFIG

db_pool = None


class AsyncMySQL:
    @classmethod
    async def execute(cls, *args, _commit=False, **kwargs):
        global db_pool
        if db_pool is None:
            db_pool = await aiomysql.create_pool(
                host=MYSQL_CONFIG["host"],
                port=MYSQL_CONFIG["port"],
                user=MYSQL_CONFIG["user"],
                password=MYSQL_CONFIG["password"],
                db=MYSQL_CONFIG["database"],
                loop=asyncio.get_event_loop()
            )

        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(*args, **kwargs)
                if _commit:
                    await conn.commit()
                return await cursor.fetchall()

    @classmethod
    async def close(cls):
        global db_pool
        db_pool.close()
        await db_pool.wait_closed()
        db_pool = None
