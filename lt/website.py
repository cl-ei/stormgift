import re
import datetime
from jinja2 import Template
from aiohttp import web
from utils.biliapi import BiliApi, CookieFetcher
from utils.dao import CookieOperator, AcceptorBlockedUser, LTWhiteList
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


async def lt_old(request):
    context = {"CDN_URL": CDN_URL}
    return render_to_response("lt/website_homepage_old.html", context=context)


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
            interval = (datetime.datetime.now() - most_recently).total_seconds()
            if interval > 3600:
                most_recently = f"约{interval // 3600}小时前"
            elif interval > 60:
                most_recently = f"约{interval // 60}分钟前"
            else:
                most_recently = f"{int(interval)}秒前"
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
        total_intimacy = 0
        for gift_name, count in rows:
            intimacy_map = {
                "总督": 20,
                "提督": 5,
                "舰长": 1,
                "小电视飞船抽奖": 5,
                "任意门抽奖": 5,
            }
            total_intimacy += intimacy_map.get(gift_name, 1)*count
            raffle_result.append({
                "gift_name": gift_name,
                "count": count
            })
        if blocked_datetime:
            title = (
                f"<h3>系统在{str(blocked_datetime)[:19]}发现你被关进了小黑屋</h3>"
                f"<p>目前挂辣条暂停中。稍后会再探测</p>"
                f"<p>最后一次抽奖时间：{str(most_recently)}</p>"
                f"<p>最近24小时内的领奖统计（24小时内累计获得亲密度：{total_intimacy}）：</p>"
            )
        else:
            title = (
                f"<h3>你现在正常领取辣条中</h3>"
                f"<p>最后一次抽奖时间：{str(most_recently)}</p>"
                f"<p>最近24小时内的领奖统计（24小时内累计获得亲密度：{total_intimacy}）：</p>"
            )

        context = {
            "CDN_URL": CDN_URL,
            "query": True,
            "raffle_result": raffle_result,
            "title": title,
        }
        return render_to_response("lt/website_homepage.html", context=context)

    elif action == "user_login":
        account = data['account']
        password = data['password']
        email = data["email"]
        if not account or not password:
            return web.Response(text="输入错误！检查你的输入!")

        if account not in await LTWhiteList.get():
            return web.Response(text=f"账户 {account} 没有权限！! 联系站长把你加到白名单才能领辣条哦。")

        flag, user_cookie = await CookieFetcher.get_cookie(account, password)
        if not flag:
            return web.Response(text=f"账户 {account} 配置错误：{user_cookie}")

        uid = re.findall(r"DedeUserID=(\d+)", user_cookie)[0]
        r, is_vip = await BiliApi.get_if_user_is_live_vip(user_cookie, user_id=uid)
        if not r:
            return web.Response(text=f"用户（uid: {uid}）你输入的数据不正确！！请检查后重新配置！！！")

        user_cookie = user_cookie + f"notice_email={email};"
        if is_vip:
            CookieOperator.add_cookie(user_cookie, "vip")
        CookieOperator.add_cookie(user_cookie, "raw")
        CookieOperator.add_cookie(user_cookie, "valid")
        return web.Response(text=f"用户（uid: {uid}）配置成功！")

    else:
        return web.Response(text=f"X")

app = web.Application()
app.add_routes([
    web.get('/lt_old', lt_old),
    web.get('/lt', lt),
    web.post('/lt/api', api),
])
web.run_app(app, port=1024)
