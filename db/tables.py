from datetime import datetime
from typing import Optional
from utils.schema import RWSchema


class LTUser(RWSchema):
    __key__ = "LT:USER"
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
    account: Optional[str]
    password: Optional[str]
    bind_qq: Optional[int]

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
        blocked_seconds = (datetime.now() - self.blocked_time).total_seconds()
        return bool(blocked_seconds > self.__block_seconds__)

    @property
    def cookie(self):
        return (
            f"bili_jct={self.bili_jct}; "
            f"DedeUserID={self.DedeUserID}; "
            f"DedeUserID__ckMd5={self.DedeUserID__ckMd5}; "
            f"sid={self.sid}; "
            f"SESSDATA={self.SESSDATA};"
        )
