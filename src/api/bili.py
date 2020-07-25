import re
import json
import base64
import time
import zlib
import struct
import asyncio
from typing import Tuple, Optional, Dict, List, Any

import aiohttp
import hashlib
import traceback
from math import floor
from typing import Union
from random import random, randint
from config import cloud_login
from utils.dao import redis_cache
from config import cloud_function_url
from src.api.schemas import *
from db.tables import LTUser
from utils.biliapi import BiliApi
from config.log4 import bili_api_logger as logging


class BiliApiError(Exception):
    def __init__(self, message: str):
        self.message = message


class _BiliApi:
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
            timeout
    ) -> Tuple[int, str]:

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

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
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
            print(f"raw response[{status}]:\n\turl: {url}\n\tcontent: {content}")
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
    def __init__(self, req_user: LTUser, raise_exc: bool = False):
        super(BiliPrivateApi, self).__init__(raise_exc)
        self.req_user = req_user
        self.headers = {"Cookie": self.req_user.cookie}

    async def post_web_hb(self, previous_interval: int, room_id: int) -> int:
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
        print(f"post_web_hb response data: {data}")
        return data["next_interval"]
