import aiohttp
import traceback
from config.log4 import lt_source_logger as logging
from config import LT_RAFFLE_ID_GETTER_HOST, LT_RAFFLE_ID_GETTER_PORT, LT_ACCEPTOR_HOST, LT_ACCEPTOR_PORT


class LtGiftMessageQ(object):
    __prize_post_url_with_raffle_id = f"http://{LT_ACCEPTOR_HOST}:{LT_ACCEPTOR_PORT}"
    __prize_post_url_without_raffle_id = f"http://{LT_RAFFLE_ID_GETTER_HOST}:{LT_RAFFLE_ID_GETTER_PORT}"

    @classmethod
    async def __request_async(cls, method, url, params, data, headers, timeout):
        headers = headers or {}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            if method == "get":
                async with session.get(url, params=params, headers=headers) as resp:
                    status_code = resp.status
                    content = await resp.text(encoding='utf-8')
                    return status_code, content

            else:
                async with session.post(url, data=data, headers=headers) as resp:
                    status_code = resp.status
                    content = await resp.text(encoding='utf-8')
                    return status_code, content

    @classmethod
    async def _request(cls, method, url, params=None, data=None, headers=None, timeout=5):
        try:
            status_code, content = await cls.__request_async(method, url, params, data, headers, timeout)
        except Exception as e:
            status_code = 5000
            content = f"Error in LtGiftMessageQ._request_async: {e}, {traceback.format_exc()}"
        return status_code, content

    @classmethod
    async def post_gift_info(cls, key_type, room_id, raffle_id=None):
        if raffle_id:
            pass
        else:
            params = {"action": "prize_notice", "key_type": key_type, "room_id": room_id}
            url = cls.__prize_post_url_without_raffle_id
            code, content = await cls._request("get", url=url, params=params)
            if code == 200 and "OK" in content:
                logging.info(f"Prize post success! {key_type}-{room_id}")
            else:
                logging.error(F"Prize room post failed. key: {key_type}-{room_id}, code: {code}, e: {content}")
