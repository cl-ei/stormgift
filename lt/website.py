import datetime
from jinja2 import Template
from aiohttp import web
from utils.biliapi import BiliApi
from utils.dao import CookieOperator, AcceptorBlockedUser
from utils.db_raw_query import AsyncMySQL
from config import CDN_URL


def render_to_response(template, context=None):
    try:
        with open(template, encoding="utf-8") as f:
            template_context = f.read()
    except IOError:
        template_context = "<center><h3>Template Does Not Existed!</h3></center>"

    template = Template(template_context)
    return web.Response(text=template.render(context or {}), content_type="text/html")


async def lt(request):
    context = {"CDN_URL": CDN_URL}
    return render_to_response("lt/website_homepage.html", context=context)


async def api(request):
    data = await request.post()

    action = data.get("action")
    if action == "add_cookie":
        uid = data['uid']
        try:
            uid = int("".join(uid.split()))
        except Exception:
            return web.Response(text="错误的uid!")

        if uid not in CookieOperator.get_white_uid_list():
            return web.Response(text=f"uid {uid} 没有权限！! 联系站长把你加到白名单才能领辣条哦。")

        SESSDATA = data['SESSDATA']
        bili_jct = data['bili_jct']
        email = data["email"]

        _test_char = SESSDATA + bili_jct + email
        if ";" in _test_char or "=" in _test_char:
            return web.Response(text="数据配置错误！请仔细阅读说明！")

        user_cookie = f"DedeUserID={uid}; SESSDATA={SESSDATA}; bili_jct={bili_jct}; notice_email={email};"
        r, is_vip = await BiliApi.get_if_user_is_live_vip(user_cookie, user_id=uid)
        if not r:
            return web.Response(text=f"用户（uid: {uid}）你输入的数据不正确！！请检查后重新配置！！！")

        if is_vip:
            CookieOperator.add_cookie(user_cookie, "vip")
        CookieOperator.add_cookie(user_cookie, "raw")
        CookieOperator.add_cookie(user_cookie, "valid")
        return web.Response(text=f"用户（uid: {uid}）配置成功！")

    elif action == "query":
        uid = data['uid']
        # -------------- query ! --------------
        try:
            uid = int("".join(uid.split()))
            assert uid > 0
        except Exception:
            return web.Response(text=f"错误的uid: {uid}, 重新输入!")

        if uid not in CookieOperator.get_white_uid_list():
            return web.Response(text=f"{uid} 你没有权限！! 联系站长把你加到白名单才能领辣条哦。")

        user_cookie = CookieOperator.get_cookie_by_uid(uid)
        if not user_cookie:
            return web.Response(text=f"用户（uid: {uid}）尚未配置，没开始领辣条。")

        r, data = await BiliApi.do_sign(user_cookie)
        if not r and "登录" in data:
            return web.Response(text=f"用户（uid: {uid}）已过期！请重新配置！！！")

        blocked_datetime = await AcceptorBlockedUser.get_blocked_datetime(uid)

        most_recently = await AsyncMySQL.execute(
            (
                "select created_time from userrafflerecord where user_id = %s order by created_time desc limit 1;"
            ), (uid,)
        )
        if most_recently:
            most_recently = most_recently[0][0]
        else:
            most_recently = "未查询到记录"

        rows = await AsyncMySQL.execute(
            (
                "select gift_name, count(raffle_id) "
                "from userrafflerecord "
                "where user_id = %s and created_time >= %s "
                "group by gift_name;"
            ), (uid, datetime.datetime.now() - datetime.timedelta(hours=24))
        )
        raffle_result = []
        for gift_name, count in rows:
            raffle_result.append({
                "gift_name": gift_name,
                "count": count
            })
        if blocked_datetime:
            main_title = f"<h3>你在{blocked_datetime}时发现被关进了小黑屋。系统会稍后再探测，目前挂辣条暂停中。</h3>"
        else:
            main_title = f"<h3>你现在正常领取辣条中</h3>"
        title = (
            f"{main_title}"
            f"<p>最后一次抽奖时间：{str(most_recently)}</p>"
            f"<p>最近24小时内的领奖统计：</p>"
        )

        context = {
            "CDN_URL": CDN_URL,
            "query": True,
            "raffle_result": raffle_result,
            "title": title
        }
        return render_to_response("lt/website_query.html", context=context)

    else:
        return web.Response(text=f"X")

app = web.Application()
app.add_routes([
    web.get('/lt', lt),
    web.post('/lt/api', api),
])
web.run_app(app, port=1024)
