import re
import rsa
import json
import time
import base64
import asyncio
import aiohttp
import hashlib
import requests
import traceback
from math import floor
from urllib import parse
from random import random
from utils.dao import redis_cache
from config.log4 import bili_api_logger as logging
from config import cloud_function_url


class CookieFetcher:
    appkey = "1d8b6e7d45233436"
    actionKey = "appkey"
    build = "520001"
    device = "android"
    mobi_app = "android"
    platform = "android"
    app_secret = "560c52ccd288fed045859ed18bffd973"
    refresh_token = ""
    access_key = ""
    cookie = ""
    csrf = ""
    uid = ""

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
        "User-Agent": "bili-universal/6570 CFNetwork/894 Darwin/17.4.0",
        "Accept-encoding": "gzip",
        "Buvid": "000ce0b9b9b4e342ad4f421bcae5e0ce",
        "Display-ID": "146771405-1521008435",
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

    @classmethod
    def calc_sign(cls, text):
        text = f'{text}{cls.app_secret}'
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    @classmethod
    async def _request(cls, method, url, params=None, data=None, json=None, headers=None, timeout=5, binary_rsp=False):
        client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))
        try:
            async with client_session as session:
                if method.lower() == "get":
                    async with session.get(url, params=params, data=data, json=json, headers=headers) as resp:
                        status_code = resp.status
                        if binary_rsp is True:
                            content = await resp.read()
                        else:
                            content = await resp.text()
                        return status_code, content

                else:
                    async with session.post(url, data=data, params=params, json=json, headers=headers) as resp:
                        status_code = resp.status
                        content = await resp.text()
                        return status_code, content
        except Exception as e:
            return 5000, f"Error happend: {e}\n {traceback.format_exc()}"

    @classmethod
    async def fetch_key(cls):
        url = 'https://passport.bilibili.com/api/oauth2/getKey'

        sign = cls.calc_sign(f'appkey={cls.appkey}')
        data = {'appkey': cls.appkey, 'sign': sign}

        status_code, content = await cls._request("post", url=url, data=data)
        if status_code != 200:
            return False, content

        try:
            json_response = json.loads(content)
        except Exception as e:
            return False, f"Not json response! {e}"

        if json_response["code"] != 0:
            return False, json_response.get("message", "unknown error!")

        return True, json_response

    @classmethod
    async def post_login_req(cls, url_name, url_password, captcha=''):
        temp_params = (
            f'actionKey={cls.actionKey}'
            f'&appkey={cls.appkey}'
            f'&build={cls.build}'
            f'&captcha={captcha}'
            f'&device={cls.device}'
            f'&mobi_app={cls.mobi_app}'
            f'&password={url_password}'
            f'&platform={cls.platform}'
            f'&username={url_name}'
        )
        sign = cls.calc_sign(temp_params)
        payload = f'{temp_params}&sign={sign}'
        url = "https://passport.bilibili.com/api/v2/oauth2/login"

        for _ in range(10):
            status_code, content = await cls._request('POST', url, params=payload)
            if status_code != 200:
                await asyncio.sleep(0.75)
                continue
            try:
                json_response = json.loads(content)
            except json.JSONDecodeError:
                continue
            return True, json_response

        return False, "Cannot login. Tried too many times."

    @classmethod
    async def fetch_captcha(cls):
        url = "https://passport.bilibili.com/captcha"
        status, content = await cls._request(method="get", url=url, binary_rsp=True)

        url = "http://152.32.186.69:19951/captcha/v1"
        str_img = base64.b64encode(content).decode(encoding='utf-8')
        _, json_rsp = await cls._request("post", url=url, json={"image": str_img})
        try:
            captcha = json.loads(json_rsp)['message']
        except json.JSONDecodeError:
            captcha = None
        return captcha

    @classmethod
    async def get_cookie(cls, account, password):
        flag, json_rsp = await cls.fetch_key()
        if not flag:
            return False, "Cannot fetch key."

        key = json_rsp['data']['key']
        hash_ = str(json_rsp['data']['hash'])

        pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(key.encode())
        hashed_password = base64.b64encode(rsa.encrypt((hash_ + password).encode('utf-8'), pubkey))
        url_password = parse.quote_plus(hashed_password)
        url_name = parse.quote_plus(account)

        flag, json_rsp = await cls.post_login_req(url_name, url_password)
        if not flag:
            return False, json_rsp

        for _try_fetch_captcha_times in range(20):
            if json_rsp["code"] != -105:
                break

            captcha = await cls.fetch_captcha()
            if not captcha:
                continue
            flag, json_rsp = await cls.post_login_req(url_name, url_password, captcha)

        if json_rsp["code"] != 0:
            return False, json_rsp.get("message", "unknown error in login!")

        cookies = json_rsp["data"]["cookie_info"]["cookies"]
        result = []
        for c in cookies:
            result.append(f"{c['name']}={c['value']}; ")

        return True, "".join(result).strip()

    @classmethod
    async def login(cls, account, password):
        flag, json_rsp = await cls.fetch_key()
        if not flag:
            return False, "Cannot fetch key."

        key = json_rsp['data']['key']
        hash_ = str(json_rsp['data']['hash'])

        pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(key.encode())
        hashed_password = base64.b64encode(rsa.encrypt((hash_ + password).encode('utf-8'), pubkey))
        url_password = parse.quote_plus(hashed_password)
        url_name = parse.quote_plus(account)

        flag, json_rsp = await cls.post_login_req(url_name, url_password)
        if not flag:
            return False, json_rsp

        for _try_fetch_captcha_times in range(20):
            if json_rsp["code"] != -105:
                break

            captcha = await cls.fetch_captcha()
            if not captcha:
                continue
            flag, json_rsp = await cls.post_login_req(url_name, url_password, captcha)

        if json_rsp["code"] != 0:
            return False, json_rsp.get("message", "unknown error in login!")

        cookies = json_rsp["data"]["cookie_info"]["cookies"]
        result = {c['name']: c['value'] for c in cookies}
        result["access_token"] = json_rsp["data"]["token_info"]["access_token"]
        result["refresh_token"] = json_rsp["data"]["token_info"]["refresh_token"]
        return True, result

    @classmethod
    async def is_token_usable(cls, cookie, access_token):
        list_url = f'access_key={access_token}&{cls.app_params}&ts={int(time.time())}'
        list_cookie = [_.strip() for _ in cookie.split(';')]
        cookie = ";".join(list_cookie).strip(";")

        params = '&'.join(sorted(list_url.split('&') + list_cookie))
        sign = cls.calc_sign(params)

        url = f'https://passport.bilibili.com/api/v2/oauth2/info?{params}&sign={sign}'
        headers = {"cookie": cookie}
        headers.update(cls.app_headers)
        status_code, content = await cls._request("get", url=url, headers=headers)
        if status_code != 200:
            return False, content

        try:
            r = json.loads(content)
            assert r["code"] == 0
            assert "mid" in r["data"]
        except Exception as e:
            return False, f"Error: {e}"

        return True, ""

    @classmethod
    async def fresh_token(cls, cookie, access_token, refresh_token):
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
        print(cookie)
        headers.update(cls.app_headers)
        status_code, content = await cls._request("post", url=url, headers=headers, params=payload)
        if status_code != 200:
            return False, content

        try:
            json_rsp = json.loads(content)
        except json.JSONDecodeError:
            return False, f"JSONDecodeError: {content}"

        if json_rsp["code"] != 0:
            return False, json_rsp["message"]

        print(f"json_rsp: {json_rsp}")
        cookies = json_rsp["data"]["cookie_info"]["cookies"]
        result = {c['name']: c['value'] for c in cookies}
        result["access_token"] = json_rsp["data"]["token_info"]["access_token"]
        result["refresh_token"] = json_rsp["data"]["token_info"]["refresh_token"]
        return True, result


class WsApi(object):
    BILI_WS_URI = "ws://broadcastlv.chat.bilibili.com:2244/sub"
    PACKAGE_HEADER_LENGTH = 16
    CONST_MESSAGE = 7
    CONST_HEART_BEAT = 2

    @classmethod
    def generate_packet(cls, action, payload=""):
        payload = payload.encode("utf-8")
        packet_length = len(payload) + cls.PACKAGE_HEADER_LENGTH
        buff = bytearray(cls.PACKAGE_HEADER_LENGTH)
        # package length
        buff[0] = (packet_length >> 24) & 0xFF
        buff[1] = (packet_length >> 16) & 0xFF
        buff[2] = (packet_length >> 8) & 0xFF
        buff[3] = packet_length & 0xFF
        # migic & version
        buff[4] = 0
        buff[5] = 16
        buff[6] = 0
        buff[7] = 1
        # action
        buff[8] = 0
        buff[9] = 0
        buff[10] = 0
        buff[11] = action
        # migic parma
        buff[12] = 0
        buff[13] = 0
        buff[14] = 0
        buff[15] = 1
        return bytes(buff + payload)

    @classmethod
    def gen_heart_beat_pkg(cls):
        return cls.generate_packet(cls.CONST_HEART_BEAT)

    @classmethod
    def gen_join_room_pkg(cls, room_id):
        uid = int(1E15 + floor(2E15 * random()))
        package = '{"uid":%s,"roomid":%s}' % (uid, room_id)
        return cls.generate_packet(cls.CONST_MESSAGE, package)

    @classmethod
    def parse_msg(cls, message):
        msg_list = []
        while message:
            length = (message[0] << 24) + (message[1] << 16) + (message[2] << 8) + message[3]
            current_msg = message[:length]
            message = message[length:]
            if len(current_msg) > 16 and current_msg[16] != 0:
                try:
                    msg = current_msg[16:].decode("utf-8", errors="ignore")
                    msg_list.append(json.loads(msg))
                except Exception as e:
                    print("e: %s, m: %s" % (e, current_msg))
        return msg_list


class BiliApi:
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/webp,image/apng,*/*;q=0.8"
        ),
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/70.0.3538.110 Safari/537.36"
        ),
    }
    USE_ASYNC_REQUEST_METHOD = True

    @classmethod
    async def _request_async(cls, method, url, headers, data, timeout):
        if url in (
            "https://api.bilibili.com/x/relation/followers?pn=1&ps=50&order=desc&jsonp=jsonp",
            "https://api.live.bilibili.com/gift/v3/smalltv/check",
            "https://api.live.bilibili.com/lottery/v1/Storm/check",
            "https://api.live.bilibili.com/activity/v1/s9/sign",
            "https://api.live.bilibili.com/xlive/web-ucenter/v1/capsule/open_capsule_by_id",
            "https://api.live.bilibili.com/xlive/web-room/v1/userRenewCard/send",
            "https://api.live.bilibili.com/gift/v2/live/receive_daily_bag",
            "https://api.live.bilibili.com/gift/v2/gift/bag_list",
            "https://api.live.bilibili.com/xlive/web-room/v1/gift/bag_list?",
            "https://api.bilibili.com/x/space/acc/info",
            "https://api.live.bilibili.com/room/v1/Room/room_init",
            "https://api.live.bilibili.com/room/v1/Area/getListByAreaID",
            "https://api.live.bilibili.com/room/v1/Room/get_info",
            "https://api.live.bilibili.com/guard/topList",

        ):
            req_json = {
                "method": method,
                "url": url,
                "headers": headers,
                "data": data if method.lower() == "post" else {},
                "params": data if method.lower() != "post" else {},
                "timeout": timeout
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.post(cloud_function_url, json=req_json) as resp:
                    status_code = resp.status
                    content = await resp.text(encoding="utf-8", errors="ignore")
                    return status_code, content

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            if method == "get":
                async with session.get(url, params=data, headers=headers) as resp:
                    status_code = resp.status
                    content = await resp.text(encoding="utf-8", errors="ignore")
                    return status_code, content

            else:
                async with session.post(url, data=data, headers=headers) as resp:
                    status_code = resp.status
                    content = await resp.text()
                    return status_code, content

    @classmethod
    async def _request(cls, method, url, headers, data, timeout, check_response_json, check_error_code):
        if headers:
            headers.update(cls.headers)
        else:
            headers = cls.headers

        if cls.USE_ASYNC_REQUEST_METHOD:
            try:
                status_code, content = await cls._request_async(method, url, headers, data, timeout)
            except asyncio.TimeoutError:
                return False, "Bili api HTTP request timeout!"

            except Exception as e:
                from config.log4 import bili_api_logger as logging
                error_message = f"Async _request Error: {e}, {traceback.format_exc()}"
                logging.error(error_message)
                return False, error_message

        else:
            fn = requests.post if method == "post" else requests.get
            try:
                r = fn(url=url, data=data, headers=headers, timeout=timeout)
            except Exception as e:
                return False, f"Response Error: {e}"

            if r.status_code != 200:
                return False, f"Status code Error: {r.status_code}"

            content = r.text

        if not check_response_json:
            return True, content

        try:
            result = json.loads(content)
        except Exception as e:
            return False, f"Not json response: {e}, content: {content}"

        if not check_error_code:
            return True, result

        if result.get("code") not in (0, "0"):
            return False, f"Error code not 0! r: {result.get('message') or result.get('msg')}"
        else:
            return True, result

    @classmethod
    async def get(cls, url, headers=None, data=None, timeout=5, check_response_json=False, check_error_code=False):
        if check_error_code:
            check_response_json = True
        return await cls._request("get", url, headers, data, timeout, check_response_json, check_error_code)

    @classmethod
    async def post(cls, url, headers=None, data=None, timeout=5, check_response_json=False, check_error_code=False):
        if check_error_code:
            check_response_json = True
        return await cls._request("post", url, headers, data, timeout, check_response_json, check_error_code)

    @classmethod
    async def search_live_room(cls, area, old_room_id=None, timeout=5):
        req_url = (
            "https://api.live.bilibili.com/room/v3/area/getRoomList"
            "?platform=web&page=1&page_size=10"
            "&parent_area_id=%s" % area
        )
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
        if not flag:
            return False, r

        room_id = 0
        room_info_list = r.get("data", {}).get("list", [])
        for info in room_info_list:
            room_id = int(info.get("roomid", 0))
            if room_id and room_id != old_room_id:
                break
        if room_id:
            return True, room_id
        else:
            return False, f"Response data error: {r}"

    @classmethod
    async def check_live_status(cls, room_id, area=None, timeout=20):
        if not room_id:
            return True, False

        req_url = f"https://api.live.bilibili.com/room/v1/Room/get_info"
        flag, response = await cls.get(
            url=req_url,
            timeout=timeout,
            data={"room_id": room_id},
            check_response_json=True,
            check_error_code=True
        )
        if not flag:
            return False, response

        live_status = response["data"]["live_status"]
        if live_status != 1:
            return True, False

        if area is None:
            return True, True

        live_area = response["data"]["parent_area_id"]
        return True, live_area == area

    @classmethod
    async def get_tv_raffle_id(cls, room_id, timeout=5):
        req_url = "https://api.live.bilibili.com/gift/v3/smalltv/check"
        flag, r = await cls.get(
            url=req_url,
            data={"roomid": room_id},
            timeout=timeout,
            check_response_json=True,
            check_error_code=True
        )
        if not flag:
            return False, r

        raffle_id_list = r.get("data", {}).get("list", [])
        if raffle_id_list:
            return True, raffle_id_list
        else:
            return False, f"Empty raffle_id_list in response."

    @classmethod
    async def get_guard_raffle_id(cls, room_id, timeout=5):
        req_url = "https://api.live.bilibili.com/lottery/v1/Lottery/check_guard?roomid=%s" % room_id
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
        if not flag:
            return flag, r

        raffle_id_list = r.get("data", [])
        if not raffle_id_list:
            return False, f"Empty raffle_id_list in response."

        return_data = {}
        for raffle in raffle_id_list:
            raffle_id = raffle.get("id", 0)
            if raffle_id:
                return_data[raffle_id] = raffle

        return_data = return_data.values()
        if return_data:
            return True, return_data
        else:
            return False, f"Cannot get valid raffleId from list, r:{r}"

    @classmethod
    async def get_guard_room_list(cls, timeout=5):
        req_url = "https://bilipage.expublicsite.com:23333/Governors/SimpleView"
        flag, r = await cls.get(req_url, timeout=timeout)
        if not flag:
            return False, r

        room_list = re.findall(r"https://live.bilibili.com/(\d+)", r)
        result = set()
        for room_id in room_list:
            try:
                result.add(int(room_id))
            except (ValueError, TypeError):
                pass

        if not result:
            return False, f"Empty list in response."
        else:
            return True, result

    @classmethod
    async def get_master_guard_count(cls, room_id, uid, timeout=5):
        req_url = f"https://api.live.bilibili.com/guard/topList"
        data = {"roomid": room_id, "ruid": uid, "page": 1}
        flag, data = await cls.get(req_url, data=data, timeout=10, check_error_code=True)
        if not flag:
            return False, data.get("message") or data.get("msg")
        guard_count = data["data"]["info"]["num"]
        return True, guard_count

    @classmethod
    async def get_user_id_by_search_way(cls, name, timeout=5):
        req_url = "https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword=%s" % name
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
        if not flag:
            return False, r

        result_list = r.get("data", {}).get("result", []) or []
        if not result_list:
            return False, "No result."

        for r in result_list:
            if r.get("uname") == name:
                return True, int(r.get("mid", 0)) or None
        return False, f"Cannot find uid from response. r: {r}"

    @classmethod
    async def add_admin(cls, name, cookie, timeout=5):
        try:
            anchor_id = re.findall(r"DedeUserID=(\d+)", cookie)[0]
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except (IndexError, ValueError, TypeError):
            return False, f"Bad cookie! {cookie}"

        req_url = "https://api.live.bilibili.com/live_user/v1/RoomAdmin/add"
        headers = {"Cookie": cookie}
        data = {
            "admin": name,
            "anchor_id": anchor_id,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        flag, r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r
        if r.get("code") == 0:
            return True, None
        else:
            return False, r.get("msg", "") or "Known error."

    @classmethod
    async def get_admin_list(cls, cookie, timeout=5):
        req_url = "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/get_by_anchor?page=1"
        headers = {"Cookie": cookie}
        flag, r = await cls.get(req_url, headers=headers, timeout=timeout,
                                check_response_json=True, check_error_code=True)
        if not flag:
            return False, r

        result = r.get("data", {}).get("data", []) or []
        return bool(result), result or "Empty admin list."

    @classmethod
    async def remove_admin(cls, uid, cookie, timeout=5):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except (IndexError, ValueError, TypeError):
            return False

        req_url = "https://api.live.bilibili.com/xlive/app-ucenter/v1/roomAdmin/dismiss"
        headers = {"Cookie": cookie}
        data = {
            "uid": uid,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        flag, r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r
        if r.get("code") == 0:
            return True, None
        else:
            return False, r.get("message", "") or "Known error."

    @classmethod
    async def join_tv(cls, room_id, gift_id, cookie, timeout=5):
        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"

        csrf_token = csrf_token_list[0]
        req_url = "https://api.live.bilibili.com/gift/v3/smalltv/join"
        headers = {"Cookie": cookie}
        data = {
            "roomid": room_id,
            "raffleId": gift_id,
            "type": "Gift",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        flag, r = await cls.post(req_url, timeout=timeout, headers=headers, data=data, check_response_json=True)
        if not flag:
            return flag, r

        result = r.get("code") == 0
        if result:
            return True, f"OK gift_type: {r.get('data', {}).get('type')}"
        else:
            return False, r.get("msg", "-")

    @classmethod
    async def join_guard(cls, room_id, gift_id, cookie, timeout=5):
        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"

        csrf_token = csrf_token_list[0]
        req_url = "https://api.live.bilibili.com/lottery/v2/Lottery/join"
        headers = {"Cookie": cookie}
        data = {
            "roomid": room_id,
            "id": gift_id,
            "type": "guard",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": "",
        }
        flag, r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r

        result = r.get("code") == 0
        if result:
            data = r.get("data", {})
            return True, f"{data.get('message')}, from {data.get('from')}"
        else:
            return False, r.get("msg", "-")

    @classmethod
    async def join_storm(cls, room_id, raffle_id, cookie, timeout=5):
        req_url = "https://api.live.bilibili.com/lottery/v1/Storm/join"
        csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        headers = {"Cookie": cookie}
        data = {
            "id": raffle_id,
            "color": 16777215,
            "captcha_token": "",
            "captcha_phrase": "",
            "roomid": room_id,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": "",
        }
        flag, data = await cls.post(req_url, timeout=timeout, headers=headers, data=data, check_response_json=True)
        print(flag, data)

    @classmethod
    async def join_pk(cls, room_id, raffle_id, cookie, timeout=5):
        req_url = "https://api.live.bilibili.com/xlive/lottery-interface/v1/pk/join"
        csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        headers = {"Cookie": cookie}
        data = {
            "roomid": room_id,
            "id": raffle_id,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        flag, data = await cls.post(req_url, timeout=timeout, headers=headers, data=data, check_response_json=True)
        if not flag:
            return False, data

        if data.get("code") == 0:
            return True, data.get("data", {}).get("title", "unknown tittle")
        else:
            return False, data.get("message")

    @classmethod
    async def send_danmaku(cls, message, room_id, cookie, color=0xffffff, timeout=5):
        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"

        csrf_token = csrf_token_list[0]
        req_url = "https://api.live.bilibili.com/msg/send"
        headers = {"Cookie": cookie}
        data = {
            "color": color,
            "fontsize": 25,
            "mode": 1,
            "msg": message,
            "rnd": int(time.time()),
            "roomid": room_id,
            "bubble": 0,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
        }
        flag, r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r

        result = r.get("code") == 0
        if result:
            return True, r.get("message", "")
        else:
            return False, r.get("message", "-")

    @classmethod
    async def enter_room(cls, room_id, cookie, timeout=5):
        headers = {"Cookie": cookie}

        req_url = f"https://api.live.bilibili.com/live_user/v1/UserInfo/get_info_in_room?roomid={room_id}"
        await cls.get(req_url, headers=headers, timeout=timeout, check_response_json=True)

        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"
        csrf_token = csrf_token_list[0]
        req_url = "https://api.live.bilibili.com/room/v1/Room/room_entry_action"
        data = {
            "room_id": room_id,
            "platform": "pc",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": "",
        }
        r = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        return r

    @classmethod
    async def get_user_face(cls, uid, timeout=10):
        req_url = f"https://api.bilibili.com/x/space/acc/info"
        data = {"mid": uid, "jsonp": "jsonp"}
        flag, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        if not flag:
            return ""
        else:
            return data.get("data", {}).get("face", "") or ""

    @classmethod
    async def get_user_name(cls, uid, timeout=10):
        req_url = f"https://api.bilibili.com/x/space/acc/info"
        data = {"mid": uid, "jsonp": "jsonp"}
        flag, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        if not flag:
            return ""
        else:
            return data.get("data", {}).get("name", "") or ""

    @classmethod
    async def get_user_info(cls, uid, timeout=10):
        req_url = f"https://api.bilibili.com/x/space/acc/info"
        data = {"mid": uid, "jsonp": "jsonp"}
        flag, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        if not flag:
            return False, data
        return True, data["data"]

    @classmethod
    async def get_uid_by_live_room_id(cls, room_id, timeout=10):
        req_url = f"https://api.live.bilibili.com/room/v1/Room/get_info"
        data = {"room_id": int(room_id)}
        flag, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        if not flag:
            return -1
        try:
            return int(data["data"]["uid"])
        except (TypeError, ValueError, IndexError, KeyError):
            return -1

    @classmethod
    async def get_live_room_info_by_room_id(cls, room_id, timeout=10):
        """

        :param room_id:
        :param timeout:
        :return:

            "uid": 50329118,
            "room_id": 7734200,
            "short_id": 6,
            "attention": 2775470,
            "online": 18963803,
            "is_portrait": false,
            "description": "<p><br /></p>",
            "live_status": 2,
            "area_id": 86,
            "parent_area_id": 2,
            "parent_area_name": "网游",
            "old_area_id": 4,
            "background": "https://i0.hdslb.com/bfs/live/516c0dbd830e898c1c3caacf2ec64c7db6395c84.jpg",
            "title": "2019英雄联盟全球总决赛",
            "user_cover": "https://i0.hdslb.com/bfs/vc/1bec3fb04a9d07735bf0e16f5a39044eada1a002.jpg",
            "keyframe": "https://i0.hdslb.com/bfs/live/7734200.jpg?10210145",
            "is_strict_room": false,
            "live_time": "0000-00-00 00:00:00",
            "tags": "LPL,英雄联盟,S9,LOL",
            "is_anchor": 0,
            "room_silent_type": "",
            "room_silent_level": 0,
            "room_silent_second": 0,
            "area_name": "英雄联盟",
            "pendants": "",
            "area_pendants": "",
        """
        req_url = f"https://api.live.bilibili.com/room/v1/Room/get_info"
        data = {"room_id": int(room_id)}
        flag, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        return flag, data["data"]

    @classmethod
    async def get_fans_list(cls, uid, timeout=10):
        req_url = f"https://api.bilibili.com/x/relation/followers?pn=1&ps=50&order=desc&jsonp=jsonp"
        flag, data = await cls.get(req_url, timeout=timeout, data={"vmid": uid}, check_error_code=True)
        result = []
        if not flag:
            return result
        for d in data.get("data", {}).get("list", []):
            result.append({"mid": d.get("mid"), "uname": d.get("uname")})
        return result

    @classmethod
    async def get_fans_count_by_uid(cls, uid, timeout=10):
        req_url = f"https://api.bilibili.com/x/relation/followers?pn=1&ps=50&order=desc&jsonp=jsonp"
        flag, data = await cls.get(req_url, timeout=timeout, data={"vmid": uid}, check_error_code=True)
        result = 0
        if not flag:
            return result
        count = data.get("data", {}).get("total", 0)
        return int(count)

    @classmethod
    async def get_guard_live_room_id_list(cls, cookie, page=1, timeout=10):
        if page >= 5:
            return []

        result = []
        req_url = f"https://api.live.bilibili.com/i/api/guard?page={page}&pageSize=10"
        flag, r = await cls.get(req_url, headers={"Cookie": cookie}, timeout=timeout, check_error_code=True)
        if not flag:
            return result

        data = r.get("data", {})
        for g in data.get("list", []):
            if "201" in g.get("expired_date", ""):
                result.append(int(g.get("ruid")))

        page_info = data.get("pageinfo", {}) or {}
        total = page_info.get("totalPage", 1)
        current = page_info.get("curPage", 1)
        if total <= current:
            return list(set(result))

        others = await cls.get_guard_live_room_id_list(cookie, page + 1)
        result.extend(others)
        return list(set(result))

    @classmethod
    async def get_live_room_id_by_uid(cls, uid, timeout=10):
        req_url = f"http://api.live.bilibili.com/room/v1/Room/getRoomInfoOld?mid={uid}"
        flag, r = await cls.get(req_url, timeout=timeout, check_error_code=True)
        if flag:
            return r.get("data", {}).get("roomid", -1) or -1
        return -1

    @classmethod
    async def get_medal_info_list(cls, cookie, timeout=10):
        req_url = f"https://api.live.bilibili.com/i/api/medal?page=1&pageSize=30"
        flag, r = await cls.get(req_url, headers={"Cookie": cookie}, timeout=timeout, check_error_code=True)
        if flag:
            return r.get("data", {}).get("fansMedalList", []) or []
        return []

    @classmethod
    async def get_bag_list(cls, cookie, timeout=10):
        # req_url = "https://api.live.bilibili.com/gift/v2/gift/bag_list"
        req_url = "https://api.live.bilibili.com/xlive/web-room/v1/gift/bag_list"
        data = {"t": int(time.time()*1000)}
        flag, r = await cls.get(req_url, headers={"Cookie": cookie}, data=data, timeout=timeout, check_error_code=True)
        if flag:
            return r.get("data", {}).get("list", []) or []
        return []

    @classmethod
    async def get_wallet(cls, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/pay/v2/Pay/myWallet?need_bp=1&need_metal=1&platform=pc"
        flag, r = await cls.get(req_url, headers={"Cookie": cookie}, timeout=timeout, check_error_code=True)
        if flag:
            return r.get("data", {}) or {}
        return {}

    @classmethod
    async def send_gift(cls, gift_id, gift_num, coin_type, bag_id, ruid, live_room_id, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/gift/v2/live/bag_send"
        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"
        csrf_token = csrf_token_list[0]

        uid_list = re.findall(r"DedeUserID=(\d+)", cookie)
        if not uid_list:
            return False, f"Bad cookie, cannot get uid."
        uid = int(uid_list[0])

        headers = {"Cookie": cookie}
        data = {
            "uid": uid,
            "gift_id": gift_id,
            "ruid": ruid,
            "send_ruid": 0,
            "gift_num": gift_num,
            "bag_id": bag_id,
            "platform": "pc",
            "biz_code": "live",
            "biz_id": live_room_id,
            "rnd": int(time.time()),
            "storm_beat_id": 0,
            "metadata": "",
            "price": 0,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        if coin_type is not None:
            data["coin_type"] = coin_type

        return await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)

    @classmethod
    async def get_guard_list(cls, uid, room_id=None, timeout=10):
        if not room_id:
            room_id = await cls.get_live_room_id_by_uid(uid)
            if room_id <= 0:
                return []

        result = {}
        page = 1
        for _ in range(20):
            req_url = f"https://api.live.bilibili.com/guard/topList?roomid={room_id}&page={page}&ruid={uid}"
            flag, data = await cls.get(req_url, timeout=timeout, check_error_code=True)

            if not flag:
                await asyncio.sleep(1)
                continue

            data = data.get("data", {}) or {}
            guard_list = data.get("list", []) + data.get("top3", [])
            for g in guard_list:
                if g["uid"] in result:
                    continue
                result[g["uid"]] = {
                    "uid": g["uid"],
                    "name": g["username"],
                    "level": g["guard_level"]
                }

            current_page = data.get("info", {}).get("page", 0)
            if page >= current_page:
                break
            else:
                page += 1
        return sorted(result.values(), key=lambda x: x["level"])

    @classmethod
    async def post_heartbeat_5m(cls, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/User/userOnlineHeart"
        headers = {"Cookie": cookie}
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"
        data = {"csrf_token": csrf_token, "csrf": csrf_token}
        return await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_error_code=True)

    @classmethod
    async def post_heartbeat_last_timest(cls, cookie, timeout=10):
        req_url = f"https://api.live.bilibili.com/relation/v1/feed/heartBeat?_={int(1000 * time.time())}"
        headers = {"Cookie": cookie}
        return await cls.get(req_url, headers=headers, timeout=timeout, check_error_code=True)

    @classmethod
    async def do_sign(cls, cookie, timeout=10):
        req_url = f"https://api.live.bilibili.com/sign/doSign"
        headers = {"Cookie": cookie}
        return await cls.get(req_url, headers=headers, timeout=timeout, check_error_code=True)

    @classmethod
    async def _sing_single_group(cls, group_id, owner_id, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/link_setting/v1/link_setting/sign_in"
        headers = {"Cookie": cookie}
        data = {
            "group_id": group_id,
            "owner_id": owner_id,
        }
        r, data = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_error_code=True)
        return r, data

    @classmethod
    async def do_sign_group(cls, cookie, timeout=10):
        req_url = "https://api.live.bilibili.com/link_group/v1/member/my_groups"
        headers = {"Cookie": cookie}
        r, data = await cls.get(req_url, headers=headers, timeout=timeout, check_error_code=True)
        if not r:
            return r, data

        groups = data.get("data", {}).get("list", []) or []
        failed_info = ""
        for g in groups:
            r, data = await cls._sing_single_group(g.get("group_id", 0), owner_id=g.get("owner_uid", 0), cookie=cookie)
            if not r:
                failed_info += f"group sign faild: {g.get('group_name', '--')}, msg: {data}.\n"
        return True, failed_info

    @classmethod
    async def do_sign_double_watch(cls, cookie, timeout=10):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        req_url = "https://api.live.bilibili.com/activity/v1/task/receive_award"
        headers = {"Cookie": cookie}
        data = {
            "task_id": "double_watch_task",
            "csrf_token": csrf_token,
            "csrf": csrf_token,
        }
        r, data = await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_error_code=True)
        return r, data

    @classmethod
    async def silver_to_coin(cls, cookie, timeout=10):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        req_url = "https://api.live.bilibili.com/pay/v1/Exchange/silver2coin"
        headers = {"Cookie": cookie}
        data = {
            "platform": "pc",
            "csrf_token": csrf_token
        }
        return await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_error_code=True)

    @classmethod
    async def get_if_user_is_live_vip(cls, cookie, user_id=None, timeout=10, return_uname=False):
        req_url = "https://api.live.bilibili.com/xlive/web-ucenter/user/get_user_info"
        headers = {"Cookie": cookie}
        r, data = await cls.get(req_url, headers=headers, timeout=timeout, check_error_code=True)
        if not r:
            if return_uname:
                return r, data, ""
            else:
                return r, data

        if isinstance(user_id, int) and user_id != data.get("data", {}).get("uid"):
            if return_uname:
                return False, "User id not match.", ""
            else:
                return False, "User id not match."

        is_vip = data.get("data", {}).get("vip") == 1
        if return_uname:
            return True, is_vip, data.get("data", {}).get("uname", "")
        else:
            return True, is_vip

    @classmethod
    async def get_live_status(cls, room_id, timeout=10):
        req_url = f"https://api.live.bilibili.com/room/v1/Room/room_init"
        data = {"id": int(room_id)}
        flag, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        if not flag:
            return False, data

        try:
            is_locked = bool(data["data"]["is_locked"])
            if is_locked:
                return True, False
            live = bool(data["data"]["live_status"])
            return True, bool(live)

        except json.JSONDecodeError:
            return False, f"Response body syn error: {data}"

    @classmethod
    async def force_get_real_room_id(cls, room_id, timeout=10):
        redis_cache_key = f"REAL_ROOM_ID_OF_{room_id}"
        real_room_id = await redis_cache.get(redis_cache_key)
        if isinstance(real_room_id, int) and real_room_id > 0:
            logging.info(f"BILI_API Get real room id: {room_id} -> {real_room_id} by redis.")
            return real_room_id

        req_url = f"https://api.live.bilibili.com/room/v1/Room/room_init"
        data = {"id": int(room_id)}
        r, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        if not r:
            logging.error(f"BILI_API Cannot get real room id of {room_id}: {data}.")
            return room_id

        real_room_id = data.get("data", {}).get("room_id")
        if isinstance(real_room_id, int) and real_room_id > 0:
            r = await redis_cache.set(redis_cache_key, real_room_id, timeout=3600*24*200)
            logging.info(f"BILI_API Get real room id: {room_id} -> {real_room_id}, saved to redis: {r}.")
            room_id = real_room_id
        return room_id

    @classmethod
    async def get_all_lived_room_count(cls, timeout=10):
        req_url = F"https://api.live.bilibili.com/room/v1/Area/getLiveRoomCountByAreaID?areaId=0"
        r, data = await cls.get(req_url, timeout=timeout, check_error_code=True)
        if not r:
            return False, data
        num = data.get("data", {}).get("num", 0)
        return num > 0, num

    @classmethod
    async def get_lived_room_id_by_page(cls, page=0, timeout=10):
        req_url = "https://api.live.bilibili.com/room/v1/Area/getListByAreaID"
        data = {
            "areaId": 0,
            "sort": "online",
            "pageSize": 500,
            "page": page,
        }
        r, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        if not r:
            return False, data
        room_list = data.get("data", []) or []
        return True, [r["roomid"] for r in room_list]

    @classmethod
    async def get_lived_room_id_list(cls, count=500, timeout=50):
        live_room_is_list = []
        for _ in range((count + 500) // 500):
            flag, data = await cls.get_lived_room_id_by_page(page=_, timeout=timeout)
            if not flag:
                return False, data
            live_room_is_list.extend(data)
            live_room_is_list = list(set(live_room_is_list))
            if len(live_room_is_list) >= count:
                return True, live_room_is_list[:count]

        return True, live_room_is_list[:count]

    @classmethod
    async def update_brief_intro(cls, cookie, description, room_id=None, timeout=50):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        url = "https://api.live.bilibili.com/room/v1/Room/update"
        data = {
            "room_id": room_id or 13369254,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "description": description,
        }
        headers = {"Cookie": cookie}
        return await cls.post(url=url, data=data, headers=headers, timeout=timeout, check_error_code=True)

    @classmethod
    async def get_storm_raffle_id(cls, room_id, timeout=10):
        url = f"https://api.live.bilibili.com/lottery/v1/Storm/check"
        param = {"roomid": room_id}
        flag, data = await cls.get(url=url, data=param, timeout=timeout, check_error_code=True)
        if flag:
            return True, data["data"]["id"]
        return flag, data

    @classmethod
    async def get_user_medal_list(cls, uid, timeout=10):
        url = f"http://api.live.bilibili.com/AppUser/medal?uid={uid}"
        flag, r = await cls.get(url=url, timeout=timeout, check_error_code=True)
        if flag:
            return True, r["data"]
        return flag, r

    @classmethod
    async def wear_medal(cls, cookie, medal_id, timeout=10):
        url = "https://api.live.bilibili.com/i/ajaxWearFansMedal"
        headers = {"Cookie": cookie}
        flag, r = await cls.get(
            url=url,
            data={"medal_id": medal_id},
            headers=headers,
            timeout=timeout,
            check_error_code=True
        )
        return flag, r

    @classmethod
    async def block_user(cls, cookie, room_id, user_id, timeout=5):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        url = "https://api.live.bilibili.com/banned_service/v2/Silent/add_block_user"
        data = {
            "roomid": room_id,
            "block_uid": user_id,
            "hour": 720,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
        }
        headers = {"Cookie": cookie}
        return await cls.post(url=url, data=data, headers=headers, timeout=timeout, check_error_code=True)

    @classmethod
    async def check_silver_box(cls, cookie, timeout=5):
        url = "https://api.live.bilibili.com/lottery/v1/SilverBox/getCurrentTask"
        headers = {"Cookie": cookie}
        flag, r = await cls.get(url=url, headers=headers, timeout=timeout, check_response_json=True)
        return flag, r

    @classmethod
    async def join_silver_box(cls, cookie, access_token, timeout=10):
        app_params = CookieFetcher.app_params
        temp_params = f'access_key={access_token}&{app_params}&ts={int(time.time())}'
        # {'code': 0, 'msg': 'ok', 'message': 'ok', 'data': {'silver': '894135', 'awardSilver': 30, 'isEnd': 0}}
        # {'code': -500, 'msg': '领取时间未到, 请稍后再试', 'message': '领取时间未到, 请稍后再试', 'data': {'surplus': 3}}
        # {'code': -903, 'msg': '已经领取过这个宝箱', 'message': '已经领取过这个宝箱', 'data': {'surplus': -8.0166666666667}}
        # {'code': 400, 'msg': '访问被拒绝', 'message': '访问被拒绝', 'data': []}
        # {'code': -800, 'msg': '未绑定手机', ...}
        sign = CookieFetcher.calc_sign(temp_params)
        url = f'https://api.live.bilibili.com/lottery/v1/SilverBox/getAward?{temp_params}&sign={sign}'
        headers = {"cookie": cookie}
        headers.update(CookieFetcher.app_headers)
        return await cls.get(url=url, headers=headers, timeout=timeout, check_response_json=True)

    @classmethod
    async def join_s9_sign(cls, cookie, timeout=5):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        url = "https://api.live.bilibili.com/activity/v1/s9/sign"
        headers = {"Cookie": cookie}
        data = {
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": "",
        }
        flag, r = await cls.post(url=url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r

        if r["code"] == 0:
            return True, r["msg"]
        else:
            return False, f"{r['code']}, msg: {r['msg']}"

    @classmethod
    async def join_s9_open_capsule(cls, cookie, timeout=5):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        data = {
            "id": 28,
            "count": 1,
            "platform": "web",
            "_": int(time.time() * 1000),
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": ""
        }
        url = "https://api.live.bilibili.com/xlive/web-ucenter/v1/capsule/open_capsule_by_id"
        headers = {"Cookie": cookie}
        flag, r = await cls.post(url=url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r

        if r["code"] == 0:
            awards = ", ".join(r['data']['text'])
            return True, f"{awards}"
        else:
            return False, r["message"]

    @classmethod
    async def send_card(cls, cookie, card_record_id, receive_uid, num, timeout=10):
        url = "https://api.live.bilibili.com/xlive/web-room/v1/userRenewCard/send"
        data = {
            "card_record_id": card_record_id,
            "recv_uid": receive_uid,
            "num": num,
            "t": int(time.time()*1000),
        }
        headers = {"Cookie": cookie}
        flag, r = await cls.get(url=url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r
        if r["code"] == 0:
            return True, ""
        else:
            return False, f"{r['code']}, {r['message']}"

    @classmethod
    async def receive_daily_bag(cls, cookie, timeout=10):
        url = "https://api.live.bilibili.com/gift/v2/live/receive_daily_bag"
        headers = {"Cookie": cookie}
        flag, r = await cls.get(url=url, headers=headers, timeout=timeout, check_response_json=True)
        if flag:
            return True, ""

        if r["code"] == 0:
            return True, ""
        else:
            return False, r["message"]

    @classmethod
    async def check_mail_box(cls, cookie, timeout=10):
        url = "https://api.live.bilibili.com/xlive/web-room/v1/propMailbox/list"
        data = {
            "page": 1,
            "page_size": 50,
            "t": int(time.time()*1000)
        }
        headers = {"Cookie": cookie}

        result = []
        error_message = ""
        for try_times in range(20):
            flag, r = await cls.get(url=url, headers=headers, data=data, timeout=timeout, check_response_json=True)
            if not flag:
                error_message = r
                continue

            if r["code"] != 0:
                return True, result

            result.extend(r["data"]["list"])

            total_page = r["data"]["page"]["total_page"]
            if data["page"] < total_page:
                data["page"] += 1
                data["t"] = int(time.time()*1000)
                continue
            else:
                return True, result
        return False, error_message

    @classmethod
    async def accept_gift_from_mail_box(cls, cookie, mail_id, timeout=10):
        url = "https://api.live.bilibili.com/xlive/web-room/v1/propMailbox/use"
        data = {"mail_id": mail_id}
        headers = {"Cookie": cookie}
        flag, r = await cls.get(url=url, headers=headers, data=data, timeout=timeout, check_response_json=True)
        if flag:
            return True, ""
        if r["code"] == 0:
            return True, ""
        else:
            return False, r["message"]

    @classmethod
    async def get_user_dynamics(cls, uid, timeout=10):
        url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history"
        params = {
            "visitor_uid": 0,
            "host_uid": uid,
            "offset_dynamic_id": 0,
        }
        flag, r = await cls.get(url=url, data=params, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r

        if r["code"] != 0:
            return False, r.get("msg") or r.get("message")

        cards = r["data"].get("cards", []) or []
        return True, cards

    @classmethod
    async def get_user_dynamic_content_and_pictures(cls, dynamic):
        card = json.loads(dynamic["card"])
        content = []
        pictures = []
        if "item" in card:
            if "description" in card["item"]:
                content.append(card["item"]["description"])
            if "pictures" in card["item"]:
                if isinstance(card["item"]["pictures"], list):
                    for p in card["item"]["pictures"]:
                        if "img_src" in p:
                            pictures.append(p["img_src"])

            if "content" in card["item"]:
                desc = card["item"]["content"]
                if "origin" in card:
                    origin = json.loads(card["origin"])
                    if "owner" in origin:
                        desc += f"\n→ 转发自{origin['owner']['name']}: {origin['desc']}"
                        pictures.append(origin['pic'])

                    elif "user" in origin:
                        desc += f"\n→ 转发自{origin['user']['name']}: {origin['item']['description']}"
                        if "pictures" in origin['item']:
                            for p in origin["item"]["pictures"]:
                                if "img_src" in p:
                                    pictures.append(p["img_src"])

                    if "image_urls" in origin:
                        for img in origin["image_urls"]:
                            pictures.append(img)

                    if "cover" in origin:
                        pictures.append(origin["cover"])

                    if "apiSeasonInfo" in origin and "title" in origin["apiSeasonInfo"]:
                        desc += f"\n\n{origin['apiSeasonInfo']['title']}"

                content.append(desc)
        else:
            if "title" in card:
                content.append(card["title"])
            if "desc" in card:
                content.append(card["desc"])
            if "dynamic" in card:
                content.append(card["dynamic"])
            if "pic" in card:
                pictures.append(card["pic"])
            if "image_urls" in card:
                for img in card["image_urls"]:
                    pictures.append(img)
            if "sketch" in card:
                content.append(card["sketch"]["title"])
                content.append(card["sketch"]["desc_text"])
                if "cover_url" in card["sketch"]:
                    pictures.append(card["sketch"]["cover_url"])

        return content, pictures

    @classmethod
    async def get_dynamic_detail(cls, dynamic_id, timeout=10):
        url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/get_dynamic_detail"
        data = {"dynamic_id": dynamic_id}
        flag, r = await cls.get(url=url, data=data, timeout=timeout, check_response_json=True)
        if not flag:
            return False, r

        if r["code"] != 0:
            return False, r.get("msg") or r.get("message")

        card = r["data"]["card"] or {}
        return bool(card), card


async def test():
    r = await BiliApi.get_uid_by_live_room_id(room_id=1108)
    print(f"f -> {r}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
