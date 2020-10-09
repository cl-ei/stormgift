import aiohttp
import datetime
from aiohttp import web
from config.log4 import cqbot_logger as logging
from utils.dao import redis_cache
from utils.cq import qq_yk
from utils.images import get_random_image


TIMES_LIMIT_K = f"LT_YK_LIMIT_{datetime.datetime.now().date()}"
TIMES_LIMIT_V = 13


async def _proc_one_sentence(group_id: int):
    key = f"LT_ONE_SENTENCE_{group_id}"
    is_second = False
    if await redis_cache.set_if_not_exists(key=key, value="1", timeout=300):
        # 第一次设置成功，则说明300秒内没有执行过
        pass
    else:
        # 300秒内执行过
        # 此时判断是不是第二次: 如果是第二次则通过; 第三次及以后block
        if await redis_cache.set_if_not_exists(key=f"{key}_FLUSH", value="1", timeout=300):
            is_second = True
        else:
            return

    count = await redis_cache.incr(TIMES_LIMIT_K)
    if count == TIMES_LIMIT_V:
        await qq_yk.send_group_msg(
            group_id=group_id,
            message=f"今日已响应召唤{TIMES_LIMIT_V}次，随即进入冬眠。（土豆出现即可重置次数限制"
        )
        return
    if count > TIMES_LIMIT_V:
        return

    async with aiohttp.request("get", "https://v1.hitokoto.cn/") as req:
        if req.status != 200:
            return ""
        r = await req.json()
        s = r.get("hitokoto") or ""

    if is_second:
        s = f"{s}\n\n为防止刷屏，5分钟内不再响应."
    await qq_yk.send_group_msg(group_id=group_id, message=s)


async def _proc_one_image(group_id):
    key = f"LT_ONE_IMG_{group_id}"
    is_second = False
    if await redis_cache.set_if_not_exists(key=key, value="1", timeout=300):
        pass
    else:
        if await redis_cache.set_if_not_exists(key=f"{key}_FLUSH", value="1", timeout=300):
            is_second = True
        else:
            return

    count = await redis_cache.incr(TIMES_LIMIT_K)
    if count == TIMES_LIMIT_V:
        await qq_yk.send_group_msg(
            group_id=group_id,
            message=f"今日已响应召唤{TIMES_LIMIT_V}次，随即进入冬眠。（土豆出现即可重置次数限制"
        )
        return
    if count > TIMES_LIMIT_V:
        return

    content = await get_random_image()
    if not content:
        return
    file_name = f"/home/wwwroot/qq_yk/images/RAND_IMG_{datetime.datetime.now()}.jpg"
    with open(file_name, "wb") as f:
        f.write(content)
    msg = f"[CQ:image,file={file_name}]"
    if is_second:
        msg += "\n为防止刷屏，5分钟内不再响应."
    await qq_yk.send_group_msg(group_id=group_id, message=msg)


async def handler(request):
    context = await request.json()
    logging.info(f"[YK]context: {context}")
    if context.get("post_type") != "message":
        return web.Response(text="", status=204)
    if context.get("message_type") != "group":
        return web.Response(text="", status=204)

    sender = context["sender"]
    user_id = sender["user_id"]

    if user_id == 448942555:
        await redis_cache.delete(TIMES_LIMIT_K)

    group_id = context["group_id"]
    msg = context["message"]

    if msg == "一言":
        await _proc_one_sentence(group_id)
    elif msg == "一图":
        await _proc_one_image(group_id)

    return web.Response(text="", status=204)
