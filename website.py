import json
from jinja2 import Template
from aiohttp import web
from utils.biliapi import BiliApi

BLACK_LIST = {
    65568410, 20932326, 312186483, 9556961, 49279889,
    51965232, 35535038, 87301592, 48386500,
    171175717, 39748080, 359496014, 3359387,
    95284802, 242134263, 294020041
}


def render_to_response(template, context=None):
    try:
        with open(template, encoding="utf-8") as f:
            template_context = f.read()
    except IOError:
        template_context = "<center><h3>Template Does Not Existed!</h3></center>"

    template = Template(template_context)
    return web.Response(text=template.render(context or {}), content_type="text/html")


async def handle(request):
    return render_to_response("website_homepage.html")


async def query(request):
    raw_uid = request.match_info['uid']
    try:
        uid = int("".join(raw_uid.split()))
        assert uid > 0
    except Exception:
        return web.Response(text=f"错误的uid： {raw_uid}，重新输入！".format())

    try:
        with open("./data/cookie.json", "r") as f:
            c = json.load(f)
        cookie_list = c["RAW_COOKIE_LIST"]
    except Exception:
        return web.Response(text="服务器内部错误！请稍后再试")

    user_cookie = ""
    char = f"DedeUserID={uid};"
    for cookie in cookie_list:
        if char in cookie:
            user_cookie = cookie
            break
    if not user_cookie:
        return web.Response(text=f"用户（USER ID: {uid}）尚未配置，没开始领辣条。")

    r, data = await BiliApi.do_sign(user_cookie)
    if not r and "登录" in data:
        return web.Response(text=f"用户（USER ID: {uid}）已过期！请重新配置！！！")

    message_list = []
    uid = str(uid)
    try:
        with open("/home/wwwroot/log/acceptor_stormgift.log", "rb") as f:
            # with open("./log/hansy.log", "rb") as f:
            _ = f.readline()
            f.seek(-1024 * 20, 2)
            lines = f.readlines()

        for line in lines[::-1]:
            line = line.decode("utf-8").strip()
            if uid in line:
                message_list.append(line)
            if len(message_list) >= 15:
                break
    except Exception as e:
        message_list = [f"未能读取。E：{e}"]
    return web.Response(text=f"用户（USER ID: {uid}）正常领取辣条中。领取记录：\n\n" + "\n".join(message_list))


async def api(request):
    data = await request.post()
    action = data["action"]
    uid = data['uid']
    try:
        uid = int("".join(uid.split()))
        assert uid in BLACK_LIST
    except Exception:
        return web.Response(text="错误的USER ID!")

    if action == "query":
        try:
            with open("./data/cookie.json", "r") as f:
                c = json.load(f)
            cookie_list = c["RAW_COOKIE_LIST"]
        except Exception:
            return web.Response(text="服务器内部错误!")

        user_cookie = ""
        char = f"DedeUserID={uid};"
        for cookie in cookie_list:
            if char in cookie:
                user_cookie = cookie
                break
        if not user_cookie:
            return web.Response(text=f"用户（USER ID: {uid}）尚未配置，没开始领辣条。")

        r, data = await BiliApi.do_sign(user_cookie)
        if not r and "登录" in data:
            return web.Response(text=f"用户（USER ID: {uid}）已过期！请重新配置！！！")
        else:
            return web.Response(text=f"用户（USER ID: {uid}）正常领取辣条中。")

    elif action == "submit":
        SESSDATA = data['SESSDATA']
        bili_jct = data['bili_jct']
        email = data["email"]

        _test_char = SESSDATA + bili_jct + email
        if ";" in _test_char or "=" in _test_char:
            return web.Response(text="数据配置错误！请仔细阅读说明！")

        user_cookie = f"DedeUserID={uid}; SESSDATA={SESSDATA}; bili_jct={bili_jct}; notice_email={email};"
        r, data = await BiliApi.do_sign(user_cookie)
        if not r and "登录" in data:
            return web.Response(text=f"用户（USER ID: {uid}）你输入的数据不正确！！请检查后重新配置！！！")

        try:
            with open("./data/cookie.json", "r") as f:
                c = json.load(f)
            cookie_list = c["RAW_COOKIE_LIST"]
        except Exception:
            return web.Response(text="服务器内部错误!")

        new_cookie_list = [user_cookie]
        char = f"DedeUserID={uid};"
        for cookie in cookie_list:
            if char not in cookie:
                new_cookie_list.append(cookie)

        with open("./data/cookie.json", "wb") as f:
            f.write(json.dumps(
                {"RAW_COOKIE_LIST": new_cookie_list},
                ensure_ascii=False,
                indent=2
            ).encode("utf-8"))
        return web.Response(text=f"用户（USER ID: {uid}）配置成功！")
    else:
        return web.Response(text="错误的请求")


app = web.Application()
app.add_routes([
    web.get('/', handle),
    web.get('/{uid}', query),
    web.post('/', api),

])
web.run_app(app, port=1024)
