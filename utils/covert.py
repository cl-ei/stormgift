import datetime


def convert_datetime_to_realworld(dt: datetime.datetime) -> str:
    return dt.replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def convert_field_to_camel_case(string: str) -> str:
    return "".join(
        word if index == 0 else word.capitalize()
        for index, word in enumerate(string.split("_"))
    )


def gen_time_prompt(interval: int) -> str:
    if interval > 3600 * 24 * 365:
        return f"很久以前"
    elif interval > 3600 * 24:
        return f"约{int(interval // (3600 * 24))}天前"
    elif interval > 3600:
        return f"约{int(interval // 3600)}小时前"
    elif interval > 60:
        return f"约{int(interval // 60)}分钟前"
    return f"{int(interval)}秒前"
