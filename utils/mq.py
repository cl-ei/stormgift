import asyncio
import aiohttp
import traceback


class SourceToRaffleMQ(object):
    req_url = "http://127.0.0.1:40000/lt/local/proc_raffle"

    @classmethod
    async def _request(cls, url, message, timeout=10):
        client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))
        try:
            async with client_session as session:
                async with session.post(url, json=message) as resp:
                    status_code = resp.status
                    if status_code in (200, 204, 206):
                        return True, ""

                    content = await resp.text()
                    return False, content

        except asyncio.TimeoutError:
            return False, f"Request timeout({timeout} second(s).)."

        except Exception as e:
            return False, f"Error happend: {e}\n {traceback.format_exc()}"

    @classmethod
    async def put(cls, danmaku, created_time, msg_from_room_id):
        message = {"danmaku": danmaku, "created_time": created_time, "msg_from_room_id": msg_from_room_id}
        return await cls._request(url=cls.req_url, message=message)


class RaffleToAcceptorMQ(object):
    @classmethod
    async def put(cls, key):
        req_url = f"http://127.0.0.1:40001/lt/local/acceptor/{key}"
        timeout = aiohttp.ClientTimeout(total=10)
        client_session = aiohttp.ClientSession(timeout=timeout)
        try:
            async with client_session as session:
                async with session.post(req_url) as resp:
                    status_code = resp.status
                    if status_code in (200, 204, 206):
                        return True, ""
                    else:
                        return False, ""
        except Exception as e:
            return False, f"Error happened in RaffleToAcceptorMQ: {e}"
