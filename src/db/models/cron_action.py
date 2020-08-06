import datetime
from typing import Optional, List
from src.db.schemas import RWSchema
from src.db.clients.mongo import RWModel


class SilverBoxRec(RWSchema):
    accept_time: datetime.datetime
    response_text: str


class UserActRec(RWModel):
    __collection__ = "user_act"

    user_id: int
    date: datetime.date

    sign_time: Optional[datetime.datetime]              # 每日签到
    sign_group_time: Optional[datetime.datetime]        # 应援团签到
    sign_group_text: Optional[str]                      # 应援团签到提示
    heart_beat_count: int = 0                           # 心跳次数
    last_heart_beat: Optional[datetime.datetime]        # 心跳时间
    silver_box: List[SilverBoxRec] = []                 # 宝箱领取记录
