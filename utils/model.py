import peewee
import asyncio
import datetime

from peewee_async import Manager, PooledMySQLDatabase
from config import MYSQL_CONFIG

mysql_db = PooledMySQLDatabase(**MYSQL_CONFIG)

loop = asyncio.get_event_loop()
objects = Manager(mysql_db, loop=loop)


class MonitorWsClient(peewee.Model):
    update_time = peewee.DateTimeField(index=True)
    name = peewee.CharField()
    value = peewee.FloatField()

    class Meta:
        database = mysql_db

    @classmethod
    async def record(cls, params):
        valid_names = (
            "valuable room",
            "api room cnt",
            "active clients",
            "broken clients",
            "total clients",
            "target clients",
            "valuable hit rate",
            "msg speed",
            "msg peak speed",
            "TCP ESTABLISHED",
            "TCP TIME_WAIT",
        )
        update_time = params.get("update_time") or datetime.datetime.now()
        insert_params = []
        for key in params:
            if key in valid_names:
                insert_params.append({"update_time": update_time, "name": key, "value": params[key]})

        if insert_params:
            await objects.execute(MonitorWsClient.insert_many(insert_params))
            return True
        else:
            return False
