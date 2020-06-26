import aiohttp
from cqhttp import CQHttp
from config import CQBOT, CQBOT_ZY, config


class CQClient:
    def __init__(self, api_root, access_token=None, timeout=5):
        self.api_root = api_root.strip().rstrip("/") + "/"
        self.timeout = timeout
        self.headers = {}
        if access_token:
            self.headers["Authorization"] = f"Bearer {access_token or ''}"

    def __getattr__(self, item):
        url = self.api_root + item

        async def parse(**data):
            try:
                status, resp_json = await self.request(url, data)
            except Exception as e:
                return False, f"Error: {e}"

            if resp_json["status"] == "failed":
                return False, resp_json["retcode"]

            return True, resp_json.get("data")

        return parse

    async def request(self, url, data):
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        client_session = aiohttp.ClientSession(timeout=timeout)
        async with client_session as session:
            async with session.post(url, json=data, headers=self.headers) as resp:
                status_code = resp.status
                resp_json = await resp.json()
                return status_code, resp_json


bot = CQHttp(**CQBOT)
bot_zy = CQHttp(**CQBOT_ZY)
qq = CQClient(api_root=CQBOT["api_root"], access_token=CQBOT["access_token"])
qq_zy = CQClient(api_root=CQBOT_ZY["api_root"], access_token=CQBOT_ZY["access_token"])

async_qq = CQClient(api_root=CQBOT["api_root"], access_token=CQBOT["access_token"])
async_zy = CQClient(api_root=CQBOT_ZY["api_root"], access_token=CQBOT_ZY["access_token"])

ml_qq = CQClient(api_root=config["ml_bot"]["api_root"], access_token=config["ml_bot"]["access_token"])
