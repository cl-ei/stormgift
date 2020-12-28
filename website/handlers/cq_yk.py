import time
import aiohttp
import datetime
from aiohttp import web
from config.log4 import cqbot_logger as logging
from utils.dao import redis_cache
from utils.cq import qq_yk
from utils.images import get_random_image


TIMES_LIMIT_V = 13


async def check_cold_time(group_id: int) -> int:
    """
    检查冷却时间。

    Returns
    -------
    resp_times: int, >= 0, 响应次数。
    """
    limit_key = f"LT_COLD_LIMIT_{group_id}"
    history = await redis_cache.get(limit_key)
    if not isinstance(history, list):
        history = []

    now = time.time()
    history = [t for t in history if now - t < 60 * 5]

    if len(history) >= 3:
        # 已经响应过3次了，直接返回4次
        return 4

    history.append(now)
    await redis_cache.set(limit_key, history)
    # 响应几次算几次，包含这一次。取值1、2、3
    return len(history)


async def _proc_one_sentence(group_id: int, is_last: bool):
    async with aiohttp.request("get", "https://v1.hitokoto.cn/") as req:
        if req.status != 200:
            return ""
        r = await req.json()
        s = r.get("hitokoto") or ""

    if is_last:
        s = f"{s}\n\n防刷屏，5分钟内不再响应."
    await qq_yk.send_group_msg(group_id=group_id, message=s)


async def _proc_one_image(group_id, is_last: bool):
    content = await get_random_image(name="yk")
    if not content:
        return
    file_name = f"/home/wwwroot/qq_yk/images/RAND_IMG_{datetime.datetime.now()}.jpg"
    with open(file_name, "wb") as f:
        f.write(content)
    msg = f"[CQ:image,file={file_name}]"
    if is_last:
        msg += "\n防刷屏，5分钟内不再响应."
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
    group_id = context["group_id"]
    msg = context["message"]

    if user_id == 448942555:
        total_limit_k = f"LT_YK_LIMIT_{datetime.datetime.now().date()}"
        await redis_cache.delete(total_limit_k)

    if msg not in ("一言", "一图"):
        return web.Response(text="", status=204)

    resp_times = await check_cold_time(group_id)
    if resp_times > 3:
        return web.Response(text="", status=204)

    # 此时检查总次数
    total_limit_k = f"LT_YK_LIMIT_{datetime.datetime.now().date()}"
    count = await redis_cache.incr(total_limit_k)
    if count == TIMES_LIMIT_V:
        # 总次数不够了
        await qq_yk.send_group_msg(
            group_id=group_id,
            message=f"今日已响应召唤{TIMES_LIMIT_V}次，随即进入冬眠。（土豆出现即可重置次数限制"
        )
        return web.Response(text="", status=204)
    elif count > TIMES_LIMIT_V:
        return web.Response(text="", status=204)

    # 此时处理
    is_last = resp_times == 3
    if msg == "一言":
        await _proc_one_sentence(group_id, is_last)
    elif msg == "一图":
        await _proc_one_image(group_id, is_last)

    return web.Response(text="", status=204)
