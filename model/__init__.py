from tortoise.models import Model
from tortoise import fields, Tortoise


class QQGroupMembers(Model):
    user_id = fields.IntField(pk=True)
    age = fields.IntField()
    area = fields.CharField(max_length=255)
    card = fields.CharField(max_length=255)
    card_changeable = fields.BooleanField()
    group_id = fields.IntField()
    join_time = fields.IntField()
    last_sent_time = fields.IntField()
    level = fields.CharField(max_length=255)
    nickname = fields.CharField(max_length=255)
    role = fields.CharField(max_length=255)
    sex = fields.CharField(max_length=255)
    title = fields.CharField(max_length=255)
    title_expire_time = fields.IntField()
    unfriendly = fields.BooleanField()

    def __str__(self):
        return f"<id: {self.user_id}-{self.nickname}>"


async def init():
    from config import MYSQL_CONFIG as M

    db_url = f"mysql://{M['user']}:{M['password']}@{M['host']}:{M['port']}/{M['database']}"
    await Tortoise.init(db_url=db_url, modules={'models': ["model"]})
    await Tortoise.generate_schemas()
