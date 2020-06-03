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


class SendGift(RWSchema):
    uid: int
    uname: str
    face: str
    giftName: str
    num: int
    guard_level: int
    rcost: int
    top_list: List[Any] = []
    timestamp: int
    giftId: int
    giftType: int
    action: str
    super: int
    super_gift_num: int
    super_batch_gift_num: int
    batch_combo_id: str
    price: int
    rnd: str = "342393440"
    newMedal: int = 0
    newTitle: int = 0
    medal: List[Any] = []
    title: str = ""
    beatId: str = ""
    biz_source: str = "live"
    metadata: str = ""
    remain: int = 1
    gold: int = 0
    silver: int = 0
    eventScore: int = 0
    eventNum: int = 0
    smalltv_msg: List[Any] = []
    specialGift: Any = None
    notice_msg: List[Any]
    smallTVCountFlag: bool = True
    capsule: Any = None
    addFollow: int = 0
    effect_block: int = 1
    coin_type: str = "silver"
    total_coin: int = 0
    effect: int = 0
    broadcast_id: int = 0
    draw: int = 0
    crit_prob: int = 0
    tag_image: str = ""
    send_master: Any = None
    is_first: bool = True
    demarcation: int = 1
    combo_stay_time: int = 0
    combo_total_coin: int = 0
    tid: int

    def __repr__(self):
        return f"<SEND_GIFT {self.giftName}({self.coin_type})*{self.num} <- {self.uname}(uid: {self.uid})>"

    def __str__(self):
        return self.__repr__()
