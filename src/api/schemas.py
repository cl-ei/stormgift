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
