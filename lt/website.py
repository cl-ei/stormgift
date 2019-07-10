import datetime
from aiohttp import web
from jinja2 import Template
from config import CDN_URL
from utils.db_raw_query import AsyncMySQL
from utils.highlevel_api import DBCookieOperator


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
    if action == "query":
        uid = data['uid']
        try:
            uid = int("".join(uid.split()))
            assert uid > 0
        except (TypeError, ValueError, AssertionError):
            return web.Response(text=f"错误的uid: {uid}, 重新输入!")

        cookie_obj = await DBCookieOperator.get_by_uid(uid)
        if cookie_obj is None:
            return web.Response(text=f"用户（uid: {uid}）没有加入到白名单，尚未配置。")

        if not cookie_obj.available:
            return web.Response(text=f"用户{cookie_obj.name}（uid: {uid}）的登录已过期，请重新登录。")

        most_recently = await AsyncMySQL.execute(
            "select created_time from userrafflerecord where user_id = %s order by created_time desc limit 1;",
            (uid, )
        )
        if most_recently:
            most_recently = most_recently[0][0]
            interval = (datetime.datetime.now() - most_recently).total_seconds()
            if interval > 3600:
                most_recently = f"约{int(interval // 3600)}小时前"
            elif interval > 60:
                most_recently = f"约{int(interval // 60)}分钟前"
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
        if (datetime.datetime.now() - cookie_obj.blocked_time).total_seconds() < 3600 * 6:
            blocked_datetime = cookie_obj.blocked_time
        else:
            blocked_datetime = None

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

        flag, obj = await DBCookieOperator.add_cookie_by_account(account=account, password=password, notice_email=email)
        if flag:
            return web.Response(text=f"用户{obj.name}（uid: {obj.DedeUserID}）配置成功！")
        else:
            return web.Response(text=f"配置失败！原因：{obj}")

    else:
        return web.Response(text=f"X")


app = web.Application()
app.add_routes([
    web.get('/lt', lt),
    web.post('/lt/api', api),
])
web.run_app(app, port=1024)
