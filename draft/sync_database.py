import os
import time
import logging
import asyncio
import aiomysql
import configparser
from utils.db_raw_query import AsyncMySQL
from config.log4 import lt_db_sync_logger as logging


loop = asyncio.get_event_loop()


class XNodeMySql:
    __conn = None

    @classmethod
    async def execute(cls, *args, **kwargs):
        if cls.__conn is None:
            config_file = "/etc/madliar.settings.ini"
            if not os.path.exists(config_file):
                config_file = "./madliar.settings.ini"
                print("Warning: LOCAL CONFIG FILE!")

            config = configparser.ConfigParser()
            config.read(config_file)

            c = config["xnode_mysql"]
            cls.__conn = await aiomysql.connect(
                host=c["host"],
                port=int(c["port"]),
                user=c["user"],
                password=c["password"],
                db=c["database"],
                loop=loop
            )
        cursor = await cls.__conn.cursor()
        await cursor.execute(*args, **kwargs)
        r = await cursor.fetchall()
        await cursor.close()
        # conn.close()
        return r


class SyncTool(object):

    @classmethod
    async def sync(cls, table_name="ltusercookie"):
        table_desc = await XNodeMySql.execute(f"desc {table_name};")
        table_fields = [row[0] for row in table_desc]
        id_index = table_fields.index("id")

        query = await XNodeMySql.execute(f"select * from {table_name} order by id desc;")

        for row in query:
            row_sql = ",".join(["%s" for _ in range(len(query[0]))])
            sql = f"INSERT INTO {table_name} VALUES({row_sql});"
            try:
                await AsyncMySQL.execute(sql, row, _commit=True)
            except Exception as e:
                err_msg = f"{e}"
                if "(1062," in err_msg:
                    fields = ",".join([f"{f}=%s" for f in table_fields])
                    sql = f"UPDATE {table_name} SET {fields} WHERE id={row[id_index]};"
                    await AsyncMySQL.execute(sql, row, _commit=True)
                else:
                    logging.error(err_msg)

    @classmethod
    async def run(cls):
        start_time = time.time()
        logging.info(f"Start Sync Database...")
        await cls.sync()

        cost = time.time() - start_time
        logging.info(f"Execute finished, cost: {cost/60:.3f} min.\n\n")


loop.run_until_complete(SyncTool.run())
