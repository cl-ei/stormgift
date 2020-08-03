import re
import json
import base64
import time
import zlib
import struct
import asyncio
from typing import Tuple, Optional, Dict, List, Any
from urllib.parse import urlencode

import aiohttp
from config import cloud_function_url
from src.api.schemas import *
from db.tables import LTUser
from config.log4 import bili_api_logger as logging
from src.api.schemas import BagItem


class BiliApiError(Exception):
    def __init__(self, message: str):
        self.message = message


class _BiliApi:
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/84.0.4147.105 Safari/537.36"
    )
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/webp,image/apng,*/*;q=0.8"
        ),
        "User-Agent": UA,
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

    def __init__(self, raise_exc: bool):
        self.raise_exc = raise_exc

    @classmethod
    async def _request(
            cls,
            method,
            url,
            headers,
            params,
            data,
            timeout: int,
    ) -> Tuple[int, str]:

        timeout = aiohttp.ClientTimeout(total=timeout)
        inner_headers: dict = dict(**cls.headers)
        if headers:
            inner_headers.update(headers)

        if url in (
            "https://api.bilibili.com/x/relation/followers?pn=1&ps=50&order=desc&jsonp=jsonp",
            "https://api.live.bilibili.com/room/v1/Room/room_init",
            "https://api.live.bilibili.com/msg/send",
        ):
            req_json = {
                "method": method,
                "url": url,
                "headers": inner_headers,
                "data": data,
                "params": params,
                "timeout": 60
            }
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(cloud_function_url, json=req_json) as resp:
                    status_code = resp.status
                    content = await resp.text(encoding="utf-8", errors="ignore")
                    return status_code, content

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method=method, url=url, params=params, data=data, headers=inner_headers) as resp:
                status_code = resp.status
                content = await resp.text(encoding="utf-8", errors="ignore")
                return status_code, content

    def parse_response_data(self, response: Dict) -> Optional[Dict]:
        api_error_code = response.get("code")
        if api_error_code != 0:
            if not self.raise_exc:
                return None

            m1 = response.get("message")
            m2 = response.get("msg")
            error_message = f"[{api_error_code}]{m1 or m2}"
            raise BiliApiError(error_message)
        return response.get("data")

    async def safe_request(
            self,
            method: str,
            url: str,
            headers: Dict[str, Any] = None,
            params: Dict[str, Any] = None,
            data: Dict[str, Any] = None,
            timeout: int = 20,
            response_class: Type[Any] = None,
    ) -> Optional[Union[Dict, List]]:
        try:
            status, content = await self._request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=data,
                timeout=timeout,
            )
            print(f"raw req: {status} from {url}\n\t{content}")
            assert status == 200
            response = json.loads(content)
        except Exception as e:
            logging.error(f"Error in request: {url}\n\te: {e}")
            return None

        data = self.parse_response_data(response)
        if not data or response_class is None:
            return data

        if isinstance(response_class, list):
            return [response_class[0](**d) for d in data]
        else:
            return response_class(**data)


class BiliPublicApi(_BiliApi):
    def __init__(self, raise_exc: bool = False):
        super(BiliPublicApi, self).__init__(raise_exc)

    async def get_live_room_info(self, user_id: int) -> Optional[RoomBriefInfo]:
        req_params = {
            "method": "get",
            "url": "https://api.live.bilibili.com/room/v1/Room/getRoomInfoOld",
            "params": {"mid": user_id},
            "response_class": RoomBriefInfo,
        }
        return await self.safe_request(**req_params)

    async def get_live_room_detail(self, room_id: int) -> Optional[RoomDetailInfo]:
        req_params = {
            "method": "get",
            "url": "https://api.live.bilibili.com/room/v1/Room/get_info",
            "params": {"room_id": int(room_id)},
            "response_class": RoomDetailInfo,
        }
        return await self.safe_request(**req_params)


class BiliPrivateApi(_BiliApi):

    HEART_BEAT_DEVICE = '["AUTO8115803053952846","10255d5f-2729-417e-a548-165beda008b1"]'

    def __init__(self, req_user: LTUser, raise_exc: bool = False):
        super(BiliPrivateApi, self).__init__(raise_exc)
        self.req_user = req_user
        self.headers = {"Cookie": self.req_user.cookie}

    @staticmethod
    async def encrypt_heart_s(data: Dict[str, Any]) -> Dict[str, Any]:
        url = "http://www.madliar.com:6000/enc"
        try:
            async with aiohttp.request("post", url=url, json=data) as resp:
                s = (await resp.json(content_type=None))["s"]
        except Exception as e:
            _ = e
            s = {}
        return s

    async def storm_heart_e(self, room_id: int) -> HeartBeatEResp:

        public_api = BiliPublicApi(raise_exc=self.raise_exc)
        room_info = await public_api.get_live_room_detail(room_id)
        parent_area_id = room_info.parent_area_id
        area_id = room_info.area_id
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://live.bilibili.com",
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        headers.update(self.headers)

        req_params = {
            "method": "post",
            "url": "https://live-trace.bilibili.com/xlive/data-interface/v1/x25Kn/E",
            "headers": headers,
            "data": urlencode({
                "id": [parent_area_id, area_id, 0, room_info.room_id],
                "device": self.HEART_BEAT_DEVICE,
                "ts": int(time.time()*1000),
                "is_patch": 0,
                "heart_beat": [],
                "ua": self.UA,
                "csrf_token": self.req_user.csrf_token,
                "csrf": self.req_user.csrf_token,
            }),
        }
        data = await self.safe_request(**req_params)
        print(f"\tpost_web_hb storm_heart_e: {data}")
        return HeartBeatEResp(
            timestamp=data['timestamp'],
            secret_key=data['secret_key'],
            heartbeat_interval=data['heartbeat_interval'],
        )

    async def storm_heart_beat(self, previous_interval: int, room_id: int) -> int:
        req_params = {
            "method": "get",
            "url": "https://live-trace.bilibili.com/xlive/rdata-interface/v1/heartbeat/webHeartBeat",
            "headers": self.headers,
            "params": {
                "hb": base64.b64encode(f"{previous_interval}|{room_id}|1|0".encode("utf-8")).decode("utf-8"),
                "pf": "web",
            },
        }
        data = await self.safe_request(**req_params)
        print(f"\tpost_web_hb response data: {data}")
        try:
            return int(data["next_interval"])
        except Exception as e:
            logging.error(f"Error in storm_heart_beat: {e}")
        return 3

    async def storm_heart_x(self, index: int, hbe: HeartBeatEResp, room_id: int):
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://live.bilibili.com',
            'Referer': f'https://live.bilibili.com/{room_id}',
        }
        headers.update(self.headers)

        s_data = {
            "t": {
                'id': [1, 34, index, 23058],
                "device": self.HEART_BEAT_DEVICE,  # LIVE_BUVID
                "ets": hbe.timestamp,
                "benchmark": hbe.secret_key,
                "time": hbe.heartbeat_interval,
                "ts": int(time.time()) * 1000,
                "ua": self.UA
            },
            "r": [2, 5, 1, 4]
        }
        t = s_data['t']

        req_params = {
            "method": "post",
            "url": "https://live-trace.bilibili.com/xlive/data-interface/v1/x25Kn/X",
            "headers": headers,
            "data": urlencode({
                's': await self.encrypt_heart_s(s_data),
                'id': t['id'],
                'device': t['device'],
                'ets': t['ets'],
                'benchmark': t['benchmark'],
                'time': t['time'],
                'ts': t['ts'],
                "ua": t['ua'],
                'csrf_token': self.req_user.csrf_token,
                'csrf': self.req_user.csrf_token,
                'visit_id': '',
            }),
        }
        data = await self.safe_request(**req_params)
        print(f"\tpost_web_hb X response data: {data}")
        return data

    async def get_bag_list(self, room_id: int = None) -> List[BagItem]:
        url = "https://api.live.bilibili.com/xlive/web-room/v1/gift/bag_list"
        params = {"t": int(time.time() * 1000)}
        if room_id:
            params["room_id"] = room_id
        data = await self.safe_request("get", url, headers=self.headers, params=params)
        gift_list = data["list"]
        return [BagItem(**i) for i in gift_list]


"""
id: [1,27,0,13369254]
device: ["AUTO8115803053952846","77dc0a5a-d11a-4544-a693-ccc1e6b9f1fc"]
ts: 1595944065926
is_patch: 1
heart_beat: [
    {
        "s":"e61da86c68d4a3ddb4420f050009eb9f24fdfbae86de08b2f78de9770c4ce22e4ca43e729472b0d53f5814233e7f67b572e2ac68d76729bb370a271932a5833e",
        "id":"[1,27,3,13369254]",
        "device": "[\"AUTO8115803053952846\",\"3b5ed910-6d73-460d-b6a0-50301a8ba075\"]",
        "ets":1595943864,
        "benchmark":"seacasdgyijfhofiuxoannn",
        "time":196,
        "ts":1595944058033,
        "ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36"
    }
]
ua: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36
csrf_token: 374b397f5b635585ed036b81f8846f33
csrf: 374b397f5b635585ed036b81f8846f33

->

{
    "code":0,
    "message":"0",
    "ttl":1,
    "data":{
        "timestamp":1595944068,
        "heartbeat_interval":60,
        "secret_key":"seacasdgyijfhofiuxoannn",
        "secret_rule":[2,5,1,4],
        "patch_status":1,
        "reason":["success"]
    }
}
"""
