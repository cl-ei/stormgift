import re
import json
import time
import zlib
import struct
import asyncio
import aiohttp
import hashlib
import traceback
from math import floor
from random import random
from config import cloud_login
from utils.dao import redis_cache
from config import cloud_function_url
from config.log4 import bili_api_logger as logging


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

    structure = struct.Struct("!I2H2I")

    @classmethod
    def parse_msg(cls, message):
        result = []
        while message:
            tuple_header = cls.structure.unpack_from(message)
            len_data, len_header, ver, opt, seq = tuple_header
            data = message[len_header:len_data]
            message = message[len_data:]

            if opt == 8:
                # join
                continue
            elif opt == 3:
                # heart beat
                continue
            elif opt == 5:
                if ver == 2:
                    data = zlib.decompress(data)
                    while data:
                        len_data, len_header, ver, opt, seq = cls.structure.unpack_from(data[:16])
                        start = len_header
                        end = len_data
                        m = json.loads(data[start:end])
                        data = data[end:]
                        result.append(m)
                else:
                    try:
                        m = json.loads(data)
                        result.append(m)
                    except Exception as e:
                        logging.error(f"e: {e}, opt5: ver: {ver} data: \n{data}\n\ntraceback: {traceback.format_exc()}")
                        continue
        return result


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

    appkey = "1d8b6e7d45233436"
    actionKey = "appkey"
    build = "520001"
    device = "android"
    mobi_app = "android"
    platform = "android"
    app_secret = "560c52ccd288fed045859ed18bffd973"

    app_headers = {
        "User-Agent": "Mozilla/5.0 BilidDroid/5.51.1(bbcallen@gmail.com)",
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

    @staticmethod
    async def login(account, password, cookie=None, access_token=None, refresh_token=None):
        req_json = {
            "account": account,
            "password": password,
            "cookie": cookie,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        async with client_session as session:
            async with session.post(cloud_login, json=req_json) as resp:
                content = await resp.text()

        try:
            json_rsp = json.loads(content)
            assert "code" in json_rsp
        except (AssertionError, json.JSONDecodeError) as e:
            logging.error(f"get_bili_login_response from cloud: {e}, content: {content}")
            return False, f"登录认证服务器返回的数据格式错误。"

        if json_rsp["code"] == -449:
            return False, f"Bili服务器繁忙，请3秒后重试。"

        if json_rsp["code"] != 0:
            return False, json_rsp.get("message") or json_rsp.get("msg") or "unknown error in login!"

        if json_rsp["data"]["status"] != 0:
            return False, "需要升级APP版本"

        cookies = json_rsp["data"]["cookie_info"]["cookies"]
        result = {c['name']: c['value'] for c in cookies}
        result["access_token"] = json_rsp["data"]["token_info"]["access_token"]
        result["refresh_token"] = json_rsp["data"]["token_info"]["refresh_token"]
        return True, result

    @classmethod
    async def _request_async(cls, method, url, headers, params, data, timeout):
        if url in (
            "https://api.bilibili.com/x/relation/followers?pn=1&ps=50&order=desc&jsonp=jsonp",
            "https://api.live.bilibili.com/room/v1/Room/room_init",
            "https://api.live.bilibili.com/msg/send",
        ):
            req_json = {
                "method": method,
                "url": url,
                "headers": headers,
                "data": data,
                "params": params,
                "timeout": timeout
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.post(cloud_function_url, json=req_json) as resp:
                    status_code = resp.status
                    content = await resp.text(encoding="utf-8", errors="ignore")
                    return status_code, content

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.request(method=method, url=url, params=params, data=data, headers=headers) as resp:
                status_code = resp.status
                content = await resp.text(encoding="utf-8", errors="ignore")
                return status_code, content

    @classmethod
    async def _request(cls, method, url, headers, data, timeout, check_response_json, check_error_code):
        if check_error_code:
            check_response_json = True

        if method.lower() == "post":
            params = {}
        else:
            params = data
            data = {}

        if headers:
            headers.update(cls.headers)
        else:
            headers = cls.headers

        try:
            status_code, content = await cls._request_async(method, url, headers, params, data, timeout)
        except asyncio.TimeoutError:
            return False, "Bili api HTTP request timeout!"
        except Exception as e:
            error_message = f"Bili api HTTP Connection Error: {e}\nurl: {url}"
            logging.error(error_message)
            return False, error_message

        if status_code != 200:
            return False, f"{status_code}"

        if "由于触发哔哩哔哩安全风控策略，该次访问请求被拒绝" in content:
            return False, "412"

        if not check_response_json:
            return True, content

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            return False, f"RESPONSE_JSON_DECODE_ERROR: {content}"

        if not check_error_code:
            return True, result

        if result.get("code") not in (0, "0"):
            return False, f"Error code not 0! r: {result.get('message') or result.get('msg')}"
        else:
            return True, result

    @classmethod
    async def get(cls, url, headers=None, data=None, timeout=5, check_response_json=False, check_error_code=False):
        return await cls._request("get", url, headers, data, timeout, check_response_json, check_error_code)

    @classmethod
    async def post(cls, url, headers=None, data=None, timeout=5, check_response_json=False, check_error_code=False):
        return await cls._request("post", url, headers, data, timeout, check_response_json, check_error_code)

    @classmethod
    async def get_living_rooms_by_area(cls, area_id, timeout=30):
        req_url = (
                "https://api.live.bilibili.com/room/v3/area/getRoomList"
                "?platform=web&page=1&page_size=10"
                "&parent_area_id=%s" % area_id
        )
        flag, result = await cls.get(req_url, timeout=timeout, check_error_code=True)
        if not flag:
            return False, result
        return True, [r["roomid"] for r in result.get("data", {}).get("list", [])]

    @classmethod
    async def check_live_status(cls, room_id, area=None, timeout=20):
        if not room_id:
            return True, False

        req_url = f"https://api.live.bilibili.com/room/v1/Room/get_info"
        flag, response = await cls.get(url=req_url, timeout=timeout, data={"room_id": room_id}, check_error_code=True)
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
    async def lottery_check(cls, room_id, timeout=30):
        req_url = "https://api.live.bilibili.com/xlive/lottery-interface/v1/lottery/Check"
        data = {"roomid": room_id}
        flag, r = await cls.get(url=req_url, data=data, timeout=timeout, check_error_code=True)
        if not flag:
            return flag, r
        data = r["data"]
        guard = data["guard"]
        gift = data["gift"]
        if guard or gift:
            return True, (guard, gift)

        return False, "Empty raffle_id_list in response."

    @classmethod
    async def get_master_guard_count(cls, room_id, uid, timeout=5):
        req_url = f"https://api.live.bilibili.com/guard/topList"
        data = {"roomid": room_id, "ruid": uid, "page": 1}
        flag, data = await cls.get(req_url, data=data, timeout=10, check_error_code=True)
        if not flag:
            return False, data

        guard_count = data["data"]["info"]["num"]
        return True, guard_count

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
            return True, r.get("message") or r.get("msg")
        else:
            return False, r.get("message") or r.get("msg")

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
        if not flag:
            return flag, data
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
    async def get_medal_info_list(cls, cookie, timeout=10):
        req_url = f"https://api.live.bilibili.com/i/api/medal?page=1&pageSize=30"
        flag, r = await cls.get(req_url, headers={"Cookie": cookie}, timeout=timeout, check_error_code=True)
        if flag:
            return r.get("data", {}).get("fansMedalList", []) or []
        return []

    @classmethod
    async def get_bag_list(cls, cookie, timeout=10):
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
    async def post_heartbeat_app(cls, cookie, access_token, timeout=30):
        if not access_token:
            return False, "No access_token."

        temp_params = f'access_key={access_token}&{cls.app_params}&ts={int(time.time())}'
        sign = cls.calc_sign(temp_params)
        url = f'https://api.live.bilibili.com/mobile/userOnlineHeart?{temp_params}&sign={sign}'
        headers = {"cookie": cookie}
        headers.update(cls.app_headers)
        return await cls.get(url, headers=headers, timeout=timeout, check_error_code=True)

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
        req_url = F"https://api.live.bilibili.com/room/v1/Area/getLiveRoomCountByAreaID"
        data = {"areaId": 0}
        r, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        if not r:
            return False, data
        num = data.get("data", {}).get("num", 0)
        return num > 0, num

    @classmethod
    async def get_lived_room_id_by_page(cls, page=0, page_size=1000, timeout=10):
        req_url = "https://api.live.bilibili.com/room/v1/Area/getListByAreaID"
        data = {
            "areaId": 0,
            "sort": "online",
            "pageSize": page_size,
            "page": page,
        }
        r, data = await cls.get(req_url, data=data, timeout=timeout, check_error_code=True)
        if not r:
            return False, data
        room_list = data.get("data", []) or []
        return True, [r["roomid"] for r in room_list]

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
    async def get_user_medal_list(cls, uid, cookie=None, timeout=10):
        url = f"https://api.live.bilibili.com/AppUser/medal?uid={uid}"
        headers = {"Cookie": cookie} if cookie else {}
        flag, r = await cls.get(url=url, timeout=timeout, headers=headers, check_error_code=True)
        if flag:
            return True, r["data"]
        return flag, r

    @classmethod
    async def get_wear_medal(cls, cookie, timeout=10):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
            user_id = re.findall(r"DedeUserID=(\d+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_toke or user_id: {e}"

        url = "https://api.live.bilibili.com/live_user/v1/UserInfo/get_weared_medal"
        data = {
            "source": 1,
            "uid": user_id,
            "target_id": user_id,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
        }
        headers = {"Cookie": cookie}
        flag, r = await cls.post(url=url, data=data, headers=headers, timeout=timeout, check_error_code=True)
        if not flag:
            return False, r

        if isinstance(r["data"], dict) and "medal_name" in r["data"]:
            return True, r["data"]
        else:
            return False, None

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
        return flag, r.get("message") or r.get("msg") or "Unknown result."

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
        app_params = cls.app_params
        temp_params = f'access_key={access_token}&{app_params}&ts={int(time.time())}'
        sign = cls.calc_sign(temp_params)
        url = f'https://api.live.bilibili.com/lottery/v1/SilverBox/getAward?{temp_params}&sign={sign}'
        headers = {"cookie": cookie}
        headers.update(cls.app_headers)
        return await cls.get(url=url, headers=headers, timeout=timeout, check_response_json=True)

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

    @classmethod
    async def change_title(cls, title, room_id, cookie, timeout=30):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        url = "https://api.live.bilibili.com/room/v1/Room/update"
        data = {
            "room_id": room_id,
            "title": title,
            "csrf_token": csrf_token,
            "csrf": csrf_token,
            "visit_id": "",
        }
        headers = {"Cookie": cookie}
        flag, r = await cls.post(url=url, data=data, headers=headers, timeout=timeout, check_response_json=True)
        if flag:
            return True, ""
        return False, r.get("message") or r.get("msg")

    @classmethod
    async def remove_dynamic(cls, dynamic_id, cookie, timeout=30):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/rm_dynamic"
        data = {
            "dynamic_id": dynamic_id,
            "csrf_token": csrf_token,
        }
        headers = {"Cookie": cookie}
        flag, r = await cls.post(url=url, data=data, headers=headers, timeout=timeout, check_error_code=True)
        return flag, r

    @classmethod
    async def watch_tv(cls, cookie, timeout=50):
        url = f'https://api.live.bilibili.com/activity/v1/task/receive_award'
        data = {'task_id': 'double_watch_task'}
        cookie = ";".join([_.strip() for _ in cookie.split(";")]).strip(";")
        headers = {
            "User-Agent": "bili-universal/6570 CFNetwork/894 Darwin/17.4.0",
            "Accept-encoding": "gzip",
            "Buvid": "000ce0b9b9b4e342ad4f421bcae5e0ce",
            "Display-ID": "146771405-1521008435",
            "Accept-Language": "zh-CN",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Connection": "keep-alive",
            "cookie": cookie
        }
        status_code, content = await cls._request_async(
            method="post",
            url=url,
            data=data,
            headers=headers,
            timeout=timeout
        )
        if status_code != 200:
            return False, f"status_code NOT 200: {status_code}, content: {content}"

        if "由于触发哔哩哔哩安全风控策略，该次访问请求被拒绝" in content:
            return False, "412"

        try:
            r = json.loads(content)
        except json.JSONDecodeError:
            return False, f"json.JSONDecodeError: {content}"

        # 返回样式:
        # {"code": -400, "msg": "奖励尚未完成", "message": "奖励尚未完成", "data": []}
        code = r["code"]
        return code == 0, r.get("message") or r.get("msg") or "no response msg."

    @classmethod
    async def add_coin(cls, aid, cookie, multiply=1, timeout=30):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        url = "https://api.bilibili.com/x/web-interface/coin/add"
        data = {
            "aid": aid,
            "multiply": multiply,
            "cross_domain": True,
            "csrf": csrf_token,
        }
        headers = {
            "Cookie": cookie,
            "referer": f"https://www.bilibili.com/video/av{aid}",
        }
        flag, r = await cls.post(url=url, data=data, headers=headers, timeout=timeout, check_error_code=True)
        return flag, r

    @classmethod
    async def fetch_bili_main_tasks(cls, cookie, timeout=30):
        url = 'https://account.bilibili.com/home/reward'
        headers = {"Cookie": cookie}
        flag, data = await cls.post(url=url, headers=headers, timeout=timeout, check_error_code=True)
        if flag:
            return flag, data["data"]
        return flag, data

    @classmethod
    async def share_video(cls, aid, cookie, timeout=30):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        url = 'https://api.bilibili.com/x/web-interface/share/add'
        data = {'aid': aid, 'jsonp': 'jsonp', 'csrf': csrf_token}
        headers = {"Cookie": cookie}
        r = await cls.post(url=url, data=data, headers=headers, timeout=timeout, check_response_json=True)
        return r

    @classmethod
    async def report(cls, cookie, oid=92580201, rpid=2447796361, reason=7, type_=1, timeout=10):
        try:
            csrf_token = re.findall(r"bili_jct=(\w+)", cookie)[0]
        except Exception as e:
            return False, f"Bad cookie, cannot get csrf_token: {e}"

        url = "https://api.bilibili.com/x/v2/reply/report"
        data = {
            "oid": oid,
            "type": type_,
            "rpid": rpid,
            "reason": reason,
            "content": "",
            "jsonp": "jsonp",
            "csrf": csrf_token
        }
        headers = {"Cookie": cookie}
        flag, msg = await cls.post(url=url, data=data, headers=headers, timeout=timeout, check_error_code=True)
        return flag, msg


async def test():
    pass


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
