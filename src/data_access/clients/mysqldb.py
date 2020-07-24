import aiomysql
from typing import Optional
from config import MYSQL_URL

mysql_pool: Optional[aiomysql.pool.Pool] = None


async def open_connection(url: str = MYSQL_URL) -> None:
    """

    Params
    ------
    url: str
        ex: mysql://user:pass@host:port/database?extra_args=values
    """
    global mysql_pool
    if mysql_pool is not None:
        return

    others = url.split("://", 1)[-1]
    user_pass, others = others.split("@", 1)
    if user_pass:
        user, password = user_pass.split(":")
    else:
        user, password = None, None

    host_port, others = others.split("/", 1)
    host, port = host_port.split(":", 1)
    port = int(port) if port else None
    db = others.split("?", 1)[0]

    mysql_pool = await aiomysql.create_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db
    )


async def close_connection() -> None:
    global mysql_pool
    if mysql_pool is None:
        return

    mysql_pool.close()
    await mysql_pool.wait_closed()
    mysql_pool = None


class AcquireCursor:
    """

    Examples
    --------
    >>> async with AcquireCursor() as cur:
    ...     print(f"cur: {type(cur)}")
    ...     await cur.execute("SELECT 10")
    ...     print(cur.description)
    ...
    ...     (r,) = await cur.fetchone()
    ...     assert r == 10
    ...
    ... await close_connection()
    """
    def __init__(self):
        self.conn = None
        self.cursor = None

    async def __aenter__(self) -> aiomysql.cursors.Cursor:
        global mysql_pool
        if mysql_pool is None:
            await open_connection()

        self.conn = await mysql_pool.acquire()
        self.cursor = cursor = await self.conn.cursor(aiomysql.DictCursor)
        return cursor

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.cursor is not None:
            await self.cursor.close()
            await mysql_pool.release(self.conn)
