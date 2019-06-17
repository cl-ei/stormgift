from jinja2 import Template
from aiohttp import web
from utils.biliapi import BiliApi

WHITE_LIST = {
    65568410, 20932326, 312186483, 9556961, 49279889,
    51965232, 35535038, 87301592, 48386500,
    171175717, 39748080, 359496014, 3359387,
    95284802, 242134263, 294020041,
    397730683, 315973598, 383823638,
    12298306,  # 丸子
    383155055,  # 元元爱喵凉
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
        return web.Response(text=f"错误的uid: {raw_uid}, 重新输入!".format())

    if uid not in WHITE_LIST:
        return web.Response(text=f"USER ID {uid} 没有权限！! 联系站长把你加到白名单才能领辣条哦。")

    with open("data/valid_cookies.txt", "r") as f:
        cookie_list = [c.strip() for c in f.readlines()]

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
            try:
                line = line.decode("utf-8").strip()
            except Exception:
                continue

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
    except Exception:
        return web.Response(text="错误的USER ID!")

    if uid not in WHITE_LIST:
        return web.Response(text=f"USER ID {uid} 没有权限！! 联系站长把你加到白名单才能领辣条哦。")

    if action == "submit":
        SESSDATA = data['SESSDATA']
        bili_jct = data['bili_jct']
        email = data["email"]

        _test_char = SESSDATA + bili_jct + email
        if ";" in _test_char or "=" in _test_char:
            return web.Response(text="数据配置错误！请仔细阅读说明！")

        user_cookie = f"DedeUserID={uid}; SESSDATA={SESSDATA}; bili_jct={bili_jct}; notice_email={email};"
        r, is_vip = await BiliApi.get_if_user_is_live_vip(user_cookie, user_id=uid)
        if not r:
            return web.Response(text=f"用户（USER ID: {uid}）你输入的数据不正确！！请检查后重新配置！！！")

        if is_vip:
            with open("data/vip_cookies.txt") as f:
                cookies = [c.strip for c in f.readlines()]

            new_vip_list = [user_cookie]
            for c in cookies:
                if f"{uid};" not in c:
                    new_vip_list.append(c)

            with open("data/vip_cookies.txt", "w") as f:
                f.write("\n".join(new_vip_list))

        # 刷新RAW
        with open("data/cookies.txt") as f:
            cookies = [c.strip for c in f.readlines()]
        raw_cookies = [user_cookie]
        for c in cookies:
            if f"{uid};" not in c:
                raw_cookies.append(c)
        with open("data/cookies.txt", "w") as f:
            f.write("\n".join(raw_cookies))

        # 刷新vaild
        with open("data/valid_cookies.txt") as f:
            cookies = [c.strip for c in f.readlines()]

        valid_cookies = [user_cookie]
        for c in cookies:
            if f"{uid};" not in c:
                valid_cookies.append(c)

        with open("data/valid_cookies.txt", "w") as f:
            f.write("\n".join(valid_cookies))

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
