import time
from datetime import datetime
from typing import Optional, List
from utils.schema import RWSchema


class LTUser(RWSchema):
    __key__ = "LT:LT_USER"
    __block_seconds__ = 60 * 5
    __UID_STR_TO_INT_MAP__ = {
        "DD": 20932326,
        "TZ": 312186483,
        "CZ": 87301592,
    }

    DedeUserID: Optional[int]
    SESSDATA: Optional[str]
    bili_jct: Optional[str]
    sid: Optional[str]
    DedeUserID__ckMd5: Optional[str]

    access_token: Optional[str]
    refresh_token: Optional[str]
    cookie_expire_time: Optional[datetime]
    notice_email: Optional[str]

    is_vip: bool = False
    available: bool = True
    name: Optional[str]
    blocked_time: Optional[datetime]
    last_accept_time: Optional[datetime]
    account: Optional[str]
    password: Optional[str]
    bind_qq: Optional[int]

    # user settings
    send_medals: List[str] = []
    percent_tv: int = 0
    percent_guard: int = 0
    percent_pk: int = 0
    percent_storm: int = 0
    percent_anchor: int = 0

    def __repr__(self):
        return f"<{self.DedeUserID}: {self.name or 'None'}>"

    def __str__(self):
        return self.__repr__()

    @property
    def uid(self):
        return self.DedeUserID

    @property
    def user_id(self):
        return self.DedeUserID

    @property
    def is_blocked(self) -> bool:
        if not self.blocked_time:
            return False
        blocked_seconds = (datetime.now() - self.blocked_time).total_seconds()
        return bool(blocked_seconds < self.__block_seconds__)

    @property
    def cookie(self):
        return (
            f"bili_jct={self.bili_jct}; "
            f"DedeUserID={self.DedeUserID}; "
            f"DedeUserID__ckMd5={self.DedeUserID__ckMd5}; "
            f"sid={self.sid}; "
            f"SESSDATA={self.SESSDATA};"
        )

    @property
    def csrf_token(self):
        return self.bili_jct


class RaffleBroadCast(RWSchema):
    __key__ = "LTS:RF_BR"

    raffle_type: str       # "guard"
    ts: int                # int(time.time())
    real_room_id: int      # room_id
    raffle_id: int         # raffle_id
    gift_name: str         # gift_name
    created_time: datetime
    expire_time: datetime
    gift_type: Optional[str]  # gift_type
    time_wait: Optional[int]  # info["time_wait"]
    max_time:  Optional[int]  # info["max_time"]

    def __str__(self):
        return f"<RfBrCst {self.raffle_type}-{self.real_room_id}.{self.raffle_id}>"

    def __repr__(self):
        return self.__str__()

    async def save(self, redis):
        await redis.zset_zadd(
            key=self.__key__,
            member_to_score={self: time.time()}
        )

    @classmethod
    async def get(cls, redis, due_time: float = None):
        if due_time is None:
            due_time = time.time()

        result = await redis.zset_zrange_by_score(
            key=cls.__key__,
            max_=due_time,
        )
        await redis.zset_zrem_by_score(
            key=cls.__key__,
            min_="-inf",
            max_=due_time,
        )
        return result
