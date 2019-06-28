import sys
import asyncio
import datetime
from utils.dao import CookieOperator
from utils.biliapi import BiliApi
from utils.model import objects, GiftRec


BiliApi.USE_ASYNC_REQUEST_METHOD = True

template = """
<div class="room-introduction">
<div class="room-introduction-scroll-wrapper">
<div class="room-introduction-content p-relative">

<div style="height: 100%; width: 25%; float: right;">
<a href="https://space.bilibili.com/20932326" 
    target="_blank">
    <span style="
        background: url('https://i0.hdslb.com/bfs/face/e0928eee0443ea39c3e0e30ffd01f3bf5ceec9cd.jpg') no-repeat; 
        margin: 5% 10% 0%; 
        background-size: 160px 160px; 
        background-color: #ffffff; 
        box-shadow: 0 0 10px #a4a4a4; 
        width: 160px; height: 160px; 
        float: left; 
        border-radius: 50%;">
    </span>
</a>
<span style="float: right; margin: 4% 4% 0%; 
    font-size: 12px; font-weight: bold;
    width: 100%; text-align: center; 
    text-shadow: 1px 1px 1px #FFF;"
>
  <span>机器人开发者:</span>
  <a style="color: #7a91f3; text-shadow: 1px 1px 1px #FFF;" 
    title="←◡←" 
    href="https://space.bilibili.com/20932326" 
    target="_blank">偷闲一天打个盹
  </a>
</span>
</div>

<div style="border-bottom: 1px dashed #ccc;">
  <p style="font-size: 22px;">
    点此去<a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
            href="http://129.204.43.2:2048/query_gifts" 
            target="_blank" rel="noopener noreferrer">
            礼物列表站点
         </a>ヾ(❀╹◡╹)ﾉﾞ❀~&nbsp;
  </p>
</div>

<div><p>更新时间: {date_time_str}</p></div>
<div><ol style="color: #7a91f3">{content}</ol></div>
</div>
</div>
</div>
"""


async def gen_intro():
    gift_price_map = {"舰长": 1, "提督": 2, "总督": 3}
    await objects.connect()
    try:
        records = await objects.execute(GiftRec.select(
            GiftRec.room_id,
            GiftRec.gift_name,
            GiftRec.expire_time,
        ).where(
            (GiftRec.expire_time > datetime.datetime.now())
            & (GiftRec.gift_name.in_(("舰长", "提督", "总督")))
        ))
        records = [[r.gift_name, r.room_id, r.expire_time] for r in records]
        records.sort(key=lambda x: (gift_price_map.get(x[0], 0), x[2], x[1]), reverse=True)
    except Exception as e:
        print(f"Error: {e}")
        records = []
    finally:
        await objects.close()

    now = datetime.datetime.now()

    def calc_expire_time(d):
        prompt = ""
        seconds = (d - now).seconds
        if seconds > 3600:
            prompt += f"{seconds // 3600}小时"
            seconds %= 3600

        if seconds > 60:
            prompt += f"{seconds // 60}分"
            seconds %= 60

        if seconds > 0:
            prompt += f"{seconds}秒"

        return prompt

    content = [
        (
            f'<li>'
            f'<a href="https://live.bilibili.com/{x[1]}" target="_blank">'
            f'{x[0][0]}->{x[1]}，{calc_expire_time(x[2])}后过期'
            f'</a>'
            f'</li>'
        ) for x in records
    ]
    date_time_str = str(now)[:23]
    return template.replace("{date_time_str}", date_time_str).replace("{content}", "".join(content))


async def main():
    cookie = CookieOperator.get_cookie_by_uid(user_id="DD")
    intro = await gen_intro()
    r = await BiliApi.update_brief_intro(cookie=cookie, description=intro)
    print(r)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
