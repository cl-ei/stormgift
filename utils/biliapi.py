import aiohttp


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
    async def search_live_room(cls, area, old_room_id=None, timeout=5):
        req_url = (
                "https://api.live.bilibili.com/room/v3/area/getRoomList"
                "?platform=web&page=1&page_size=10"
                "&parent_area_id=%s" % area
        )
        r = {}
        timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout, headers=cls.headers) as session:
            try:
                async with session.get(req_url) as resp:
                    if resp.status == 200:
                        r = await resp.json()
            except Exception:
                pass

        room_id = 0
        room_info_list = r.get("data", {}).get("list", [])
        for info in room_info_list:
            room_id = int(info.get("roomid", 0))
            if room_id and room_id != old_room_id:
                break
        return room_id

    @classmethod
    async def check_live_status(cls, room_id, area=None, timeout=5):
        if not room_id:
            return False

        req_url = (
            "https://api.live.bilibili.com/AppRoom/index"
            "?platform=android&room_id=%s" % room_id
        )
        r = {}
        timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout, headers=cls.headers) as session:
            try:
                async with session.get(req_url) as resp:
                    if resp.status == 200:
                        r = await resp.json()
            except Exception as e:
                print(e)
                pass

        data = r.get("data", {})
        is_lived = data.get("status") == "LIVE"
        if area is None:
            return is_lived
        else:
            return is_lived and data.get("area_v2_parent_id") == area
