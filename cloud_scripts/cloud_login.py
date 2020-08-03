# -*- coding: utf-8 -*-
import sys
import json
import time
import base64
import hashlib
import logging
import requests
import traceback
from urllib import parse


logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)


class CookieFetcher:
    appkey = "1d8b6e7d45233436"
    actionKey = "appkey"
    build = "520001"
    device = "android"
    mobi_app = "android"
    platform = "android"
    app_secret = "560c52ccd288fed045859ed18bffd973"

    pc_headers = {
        "Accept-Language": "zh-CN,zh;q=0.9",
        "accept-encoding": "gzip, deflate",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_3) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/62.0.3202.94 Safari/537.36"
        ),
    }
    app_headers = {
        "User-Agent": "Mozilla/5.0 BiliDroid/5.58.0 (bbcallen@gmail.com)",
        "Accept-encoding": "gzip",
        "Buvid": "XZ11bfe2654a9a42d885520a680b3574582eb3",
        "Display-ID": "146771405-1521008435",
        "Device-Guid": "2d0bbec5-df49-43c5-8a27-ceba3f74ffd7",
        "Device-Id": "469a6aaf431b46f8b58a1d4a91d0d95b202004211125026456adffe85ddcb44818",
        "Accept-Language": "zh-CN",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Connection": "keep-alive",
    }
    app_params = (
        f'actionKey={actionKey}'
        f'&appkey={appkey}'
        f'&build={build}'
        f'&device={device}'
        f'&mobi_app={mobi_app}'
        f'&platform={platform}'
    )

    session = requests.session()

    @classmethod
    def record_captcha(cls, source, result):
        pass

    @classmethod
    def calc_sign(cls, text):
        text = f'{text}{cls.app_secret}'
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    @classmethod
    def _request(cls, method, url, params=None, data=None, json=None, headers=None, timeout=5, binary_rsp=False):
        try:
            if method.lower() == "get":
                f = cls.session.get
            else:
                f = cls.session.post

            r = f(url=url, params=params, data=data, json=json, headers=headers, timeout=timeout)
            status_code = r.status_code
            if binary_rsp is True:
                content = r.content
            else:
                content = r.content.decode("utf-8", errors="ignore")
            return status_code, content

        except Exception as e:
            return 5000, f"Error happend: {e}\n {traceback.format_exc()}"

    @classmethod
    def fetch_key(cls):
        url = 'https://passport.bilibili.com/api/oauth2/getKey'

        sign = cls.calc_sign(f'appkey={cls.appkey}')
        data = {'appkey': cls.appkey, 'sign': sign}

        status_code, content = cls._request("post", url=url, data=data)
        if status_code != 200:
            return False, content

        if "由于触发哔哩哔哩安全风控策略，该次访问请求被拒绝。" in content:
            return False, "412"

        try:
            json_response = json.loads(content)
        except json.JSONDecodeError:
            return False, f"RESPONSE_JSON_DECODE_ERROR: {content}"

        if json_response["code"] != 0:
            return False, json_response.get("message") or json_response.get("msg") or "unknown error!"

        return True, json_response

    @classmethod
    def post_login_req(cls, url_name, url_password, captcha=''):
        params = [
            f'actionKey={cls.actionKey}',
            f'appkey={cls.appkey}',
            f'build={cls.build}',
            f'device={cls.device}',
            f'mobi_app={cls.mobi_app}',
            f'platform={cls.platform}',
        ] + [
            f'captcha={captcha}',
            f'password={url_password}',
            f'username={url_name}'
        ]
        text = "&".join(sorted(params))

        text_with_appsecret = f'{text}{cls.app_secret}'
        sign = hashlib.md5(text_with_appsecret.encode('utf-8')).hexdigest()
        payload = f'{text}&sign={sign}'
        url = "https://passport.bilibili.com/api/v3/oauth2/login"

        for _ in range(10):
            status_code, content = cls._request('POST', url, params=payload, headers=cls.app_headers)
            if status_code != 200:
                time.sleep(0.75)
                continue
            try:
                json_response = json.loads(content)
            except json.JSONDecodeError:
                continue
            return True, json_response

        return False, "Cannot login. Tried too many times."

    @classmethod
    def fetch_captcha(cls):
        url = "https://passport.bilibili.com/captcha"
        status, content = cls._request(method="get", url=url, binary_rsp=True)

        url = "http://152.32.186.69:19951/captcha/v1"
        str_img = base64.b64encode(content).decode(encoding='utf-8')
        _, json_rsp = cls._request("post", url=url, json={"image": str_img})
        try:
            captcha = json.loads(json_rsp)['message']
        except json.JSONDecodeError:
            captcha = None
        return str_img, captcha

    @classmethod
    def login(cls, account, password):
        flag, json_rsp = cls.fetch_key()
        if not flag:
            return 500, {"code": 5000, "msg": "Cannot fetch key."}

        key = json_rsp['data']['key']
        hash_str = str(json_rsp['data']['hash'])

        def get_hashed_password(k, h, p):
            url = "https://www.madliar.com/calc_sign"
            data = {"key": k, "hash_str": h, "password": p}
            r = requests.post(url=url, data=data)
            if r.status_code != 200:
                return
            return r.content

        hashed_password = get_hashed_password(k=key, h=hash_str, p=password)
        if not hashed_password:
            return 500, {"code": 6003, "msg": "MADLIAR.com cannot access!"}

        url_password = parse.quote_plus(hashed_password)
        url_name = parse.quote_plus(account)

        for _try_times in range(10):
            flag, json_rsp = cls.post_login_req(url_name, url_password)
            if not flag:
                return 500, {"code": 500, "msg": json_rsp}

            if json_rsp["code"] != -449:
                break
            time.sleep(0.5)

        if json_rsp["code"] == -449:
            return 500, {"code": -449, "msg": "登录失败: -449"}

        if json_rsp["code"] == -105:  # need captchar
            for _try_fetch_captcha_times in range(20):
                source, result = cls.fetch_captcha()
                if not result:
                    continue
                flag, json_rsp = cls.post_login_req(url_name, url_password, captcha=result)

                if json_rsp["code"] == -105:  # need captchar
                    continue

                if json_rsp["code"] == 0:
                    cls.record_captcha(source=source, result=result)
                break

        if json_rsp["code"] == 0:
            return 200, json_rsp

        return 503, {"code": 504, "msg": json_rsp}

    @classmethod
    def is_token_usable(cls, cookie, access_token):
        list_url = f'access_key={access_token}&{cls.app_params}&ts={int(time.time())}'
        list_cookie = [_.strip() for _ in cookie.split(';')]
        cookie = ";".join(list_cookie).strip(";")

        params = '&'.join(sorted(list_url.split('&') + list_cookie))
        sign = cls.calc_sign(params)

        url = f'https://passport.bilibili.com/api/v3/oauth2/info?{params}&sign={sign}'
        headers = {"cookie": cookie}
        headers.update(cls.app_headers)
        status_code, content = cls._request("get", url=url, headers=headers)
        if status_code != 200:
            return False, content

        try:
            r = json.loads(content)
            assert r["code"] == 0
            assert "mid" in r["data"]
        except Exception as e:
            return False, f"Error: {e}"

        return True, r

    @classmethod
    def fresh_token(cls, cookie, access_token, refresh_token):
        list_url = (
            f'access_key={access_token}'
            f'&access_token={access_token}'
            f'&{cls.app_params}'
            f'&refresh_token={refresh_token}'
            f'&ts={int(time.time())}'
        )

        # android param! 严格
        list_cookie = [_.strip() for _ in cookie.split(';')]
        cookie = ";".join(list_cookie).strip(";")

        params = ('&'.join(sorted(list_url.split('&') + list_cookie)))
        sign = cls.calc_sign(params)
        payload = f'{params}&sign={sign}'

        url = f'https://passport.bilibili.com/api/v2/oauth2/refresh_token'
        headers = {"cookie": cookie}
        headers.update(cls.app_headers)
        status_code, content = cls._request("post", url=url, headers=headers, params=payload)
        if status_code != 200:
            return False, content

        try:
            json_rsp = json.loads(content)
        except json.JSONDecodeError:
            return False, f"JSONDecodeError: {content}"

        if json_rsp["code"] != 0:
            return False, json_rsp["message"]

        cookies = json_rsp["data"]["cookie_info"]["cookies"]
        result = {c['name']: c['value'] for c in cookies}
        result["access_token"] = json_rsp["data"]["token_info"]["access_token"]
        result["refresh_token"] = json_rsp["data"]["token_info"]["refresh_token"]
        return True, result


def main_handler(event, context):
    request_params = json.loads(event["body"])

    account = request_params["account"]
    password = request_params["password"]
    cookie = request_params.get("cookie")
    access_token = request_params.get("access_token")
    refresh_token = request_params.get("refresh_token")

    if cookie and access_token and refresh_token:
        flag, result = CookieFetcher.fresh_token(
            cookie=cookie,
            access_token=access_token,
            refresh_token=refresh_token
        )
        if flag:
            return {
                "headers": {"Content-Type": "application/json"},
                "statusCode": 200,
                "body": json.dumps(result),
            }

    status_code, content = CookieFetcher.login(account=account, password=password)
    if isinstance(content, dict):
        content = json.dumps(content)

    return {
        "headers": {"Content-Type": "application/json"},
        "statusCode": 200,
        "body": content,
    }


if __name__ == "__main__":
    import asyncio

    async def main():
        from aiohttp import web

        async def login(request):
            request_params = await request.text()
            r = main_handler({"body": request_params}, None)
            return web.Response(status=r["statusCode"], text=r["body"], content_type=r["headers"]["Content-Type"])

        app = web.Application()
        app.add_routes([web.route('*', '/login', login)])
        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, '127.0.0.1', 4096)
        await site.start()
        print(f"Started. http://127.0.0.1:4096/login")
        while True:
            await asyncio.sleep(100)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
