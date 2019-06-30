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
  <p style="font-size: 14px;">
    点此去<a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
            href="http://129.204.43.2:2048/query_gifts" 
            target="_blank" rel="noopener noreferrer">
            礼物列表站点
         </a>ヾ(❀╹◡╹)ﾉﾞ❀~&nbsp;
  </p>
  <p style="font-size: 14px;">
    想看看都谁中奖了？➟ <a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
            href="http://129.204.43.2:2048/query_raffles" 
            target="_blank" rel="noopener noreferrer">
            获奖记录
         </a>
  </p>
</div>

<div><p>更新时间: {date_time_str}</p></div>
<div><ol style="color: #7a91f3">{content}</ol></div>
</div>
</div>
</div>
"""


async def gen_intro():
    await objects.connect()
    r = await objects.execute(GiftRec.select(
        GiftRec.room_id,
        GiftRec.gift_name
    ).where(
        (GiftRec.expire_time > datetime.datetime.now())
        & (GiftRec.gift_name.in_(("舰长", "提督", "总督")))
    ))
    await objects.close()

    gifts = {}
    for e in r:
        gifts.setdefault(e.room_id, []).append(e.gift_name)

    result = []
    for room_id, gifts_list in gifts.items():
        display = []
        intimacy = 0

        z = [n for n in gifts_list if n == "总督"]
        if z:
            display.append(f"{len(z)}个总督")
            intimacy += 20*len(z)
        t = [n for n in gifts_list if n == "提督"]
        if t:
            display.append(f"{len(t)}个提督")
            intimacy += 5 * len(t)
        j = [n for n in gifts_list if n == "舰长"]
        if j:
            display.append(f"{len(j)}个舰长")
            intimacy += len(j)

        result.append((room_id, "、".join(display), intimacy))
    result.sort(key=lambda x: x[2], reverse=True)

    content = [
        (
            f'<li>'
            f'<a href="https://live.bilibili.com/{x[0]}" target="_blank">'
            f'{x[0]}: {x[1]}，{x[2]}点亲密度'
            f'</a>'
            f'</li>'
        ) for x in result
    ]
    date_time_str = str(datetime.datetime.now())[:23]
    return template.replace("{date_time_str}", date_time_str).replace("{content}", "".join(content))


async def main():
    cookie = CookieOperator.get_cookie_by_uid(user_id="DD")
    intro = await gen_intro()
    r = await BiliApi.update_brief_intro(cookie=cookie, description=intro)
    print(r)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
