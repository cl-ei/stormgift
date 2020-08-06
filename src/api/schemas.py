import datetime
from typing import *
from pydantic import BaseModel, BaseConfig


def convert_datetime_to_realworld(dt: datetime.datetime) -> str:
    return dt.replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def convert_field_to_camel_case(string: str) -> str:
    return "".join(
        word if index == 0 else word.capitalize()
        for index, word in enumerate(string.split("_"))
    )


class RWSchema(BaseModel):
    class Config(BaseConfig):
        allow_population_by_field_name = True
        json_encoders = {datetime.datetime: convert_datetime_to_realworld}
        alias_generator = convert_field_to_camel_case
        orm_mode = True


class RoomBriefInfo(RWSchema):
    roomStatus: int
    roundStatus: int
    liveStatus: int = 0
    url: str
    title: str
    cover: str  # url
    online: int
    roomid: int
    broadcast_type: int = 0
    online_hidden: int = 0


class RoomDetailInfo(RWSchema):
    uid: int
    room_id: int
    short_id: int
    attention: int
    online: int
    is_portrait: bool
    description: str
    live_status: int
    area_id: int
    parent_area_id: int
    parent_area_name: str
    old_area_id: int
    background: str
    title: str
    user_cover: str
    keyframe: str
    is_strict_room: bool
    live_time: str
    tags: str
    is_anchor: int
    room_silent_type: str
    room_silent_level: int
    room_silent_second: int
    area_name: str
    pendants: str
    area_pendants: str


class BagItem(RWSchema):

    class CountItem(RWSchema):
        num: int
        text: str

    bag_id: int
    gift_id: int
    gift_name: str
    gift_num: int
    gift_type: int
    expire_at: float
    corner_mark: str                # "1天"
    corner_color: str               # ""
    count_map: List[CountItem]
    bind_roomid: int
    bind_room_text: str             # ""
    type: int
    card_image: str                 # ""
    card_gif: str                   # ""
    card_id: int                    # 0
    card_record_id: int             # 0
    is_show_send: bool              # false

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"<BagItem_{self.bag_id}: {self.corner_mark}.{self.gift_name}*{self.gift_num}>"


class HeartBeatEResp(RWSchema):
    timestamp: int
    secret_key: str
    heartbeat_interval: int


class UserMedalInfo(RWSchema):
    roomid: Optional[int]           # 550 short

    target_id: int                  # 勋章主播的uid
    target_name: str                # 主播的name
    master_available: int           # 1
    master_status: int              # 1

    medal_id: int
    medal_name: str                 # 勋章名
    score: int
    level: int
    last_wear_time: int             # 时间戳 到秒
    intimacy: int                   # 亲密度
    next_intimacy: int
    day_limit: int
    today_feed: int
    today_intimacy: int             # 今日投喂
    is_lighted: int                 # 0 or 1

    status: int                     # 0
    source: int                     # 1
    receive_channel: int            # 1
    is_receive: int                 # 1
    receive_time: datetime.datetime

    guard_type: int                 # 0
    guard_level: int                # 0
    guard_medal_title: str          # "未开启加成"
    can_delete: bool

    medal_color: int
    medal_color_start: int
    medal_color_end: int
    medal_color_border: int

    @property
    def left_intimacy(self) -> int:
        left = self.today_feed - self.day_limit
        return max(0, left)
