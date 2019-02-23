import re
import json
import time
import asyncio
import requests
from random import random
from math import floor


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

    @classmethod
    async def _request(cls, method, url, headers, data, timeout, check_response_json, check_error_code):
        if headers:
            headers.update(cls.headers)
        else:
            headers = cls.headers
        fn = requests.post if method == "post" else requests.get
        try:
            r = fn(url=url, data=data, headers=headers, timeout=timeout)
        except Exception as e:
            return False, f"Response Error: {e}"

        if r.status_code != 200:
            return False, f"Status code Error: {r.status_code}"

        if not check_response_json:
            return True, r.text

        try:
            result = json.loads(r.text)
        except Exception as e:
            return False, f"Not json response: {e}"

        if not check_error_code:
            return True, result

        if result.get("code") not in (0, "0"):
            return False, f"Error code not 0! r: {result.get('message')}"
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
    async def check_live_status(cls, room_id, area=None, timeout=5):
        if not room_id:
            return True, False

        req_url = (
            "https://api.live.bilibili.com/AppRoom/index"
            "?platform=android&room_id=%s" % room_id
        )
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
        if not flag:
            return False, r

        data = r.get("data", {})
        is_lived = data.get("status") == "LIVE"
        if area is None:
            return True, is_lived
        else:
            return True, is_lived and data.get("area_v2_parent_id") == area

    @classmethod
    async def get_tv_raffle_id(cls, room_id, timeout=5):
        req_url = "https://api.live.bilibili.com/gift/v3/smalltv/check?roomid=%s" % room_id
        flag, r = await cls.get(req_url, timeout=timeout, check_response_json=True, check_error_code=True)
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
        req_url = "https://dmagent.chinanorth.cloudapp.chinacloudapi.cn:23333/Governors/View"
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
    async def send_danmaku(cls, message, room_id, cookie, color=0xffffff, timeout=5):
        csrf_token_list = re.findall(r"bili_jct=(\w+)", cookie)
        if not csrf_token_list:
            return False, f"Cannot get csrf_token!"

        csrf_token = csrf_token_list[0]
        req_url = "https://live.bilibili.com/msg/send"
        headers = {"Cookie": cookie}
        data = {
            "color": color,
            "fontsize": 25,
            "mode": 1,
            "msg": message,
            "rnd": int(time.time()),
            "roomid": room_id,
            "csrf_token": csrf_token,
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
        await cls.post(req_url, headers=headers, data=data, timeout=timeout, check_response_json=True)


async def test():
    print("Running test.")
    r = await BiliApi.join_guard(
        20932326,
        3232,
        "LIVE_BUVID="
    )
    print(f"r: {r}")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
    loop.close()
