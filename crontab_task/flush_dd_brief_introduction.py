import asyncio
import datetime
import jinja2
from utils.highlevel_api import DBCookieOperator
from utils.biliapi import BiliApi
from utils.db_raw_query import AsyncMySQL


BiliApi.USE_ASYNC_REQUEST_METHOD = True

template_text = """
<div class="room-introduction">
<div class="room-introduction-scroll-wrapper">
<div class="room-introduction-content p-relative">
<div style="height: 100%;width: 160px;margin-right: 100px;float: right;">
<a href="https://jq.qq.com/?_wv=1027&k=5rxXTM7" target="_blank">
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
<span style="float: left;
  margin-top: 15px;
  font-size: 12px;
  font-weight: bold;
  width: 190px;
  text-align: center;
  text-shadow: 1px 1px 3px #9c9c9c;"
>
  偷闲一天打个盹<br>
  <a style="color: #7a91f3;" 
    title="←◡←" 
    href="https://jq.qq.com/?_wv=1027&k=5rxXTM7">
    加入宝藏站点交流群:159855203
  </a>
</span>
</div>

<div style="border-bottom: 1px dashed #ccc;font-size: 14px;">
  <p>点此去
    <a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
      href="https://www.madliar.com/lt/query_gifts" target="_blank">
      礼物列表站点
    </a>ヾ(❀╹◡╹)ﾉﾞ❀~&nbsp;
  </p>
  <p>想看看都谁中奖了？➟ 
    <a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
      href="https://www.madliar.com/lt/query_raffles" target="_blank">获奖记录</a>
  </p>
  <p>收藏歌单？➟ 
    <a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
      href="https://www.madliar.com/music" target="_blank">音乐列表</a>
  </p>
</div>

<div><p>更新时间: {{ update_time }}</p></div>
<div><ol style="color: #7a91f3">
{% for row in guard_list %}<li><a href="https://live.bilibili.com/{{ row.room_id }}" target="_blank">
{{ row.room_id }}: {{ row.prompt }}，{{ row.intimacy }}点亲密度</a></li>
{% endfor %}
</ol></div></div></div></div>
"""


async def gen_intro():
    now = datetime.datetime.now()
    guard_query = await AsyncMySQL.execute(
        "select room_id, gift_name from guard where expire_time > %s and gift_name in %s;",
        (now, ("舰长", "提督", "总督"))
    )

    room_id_list = [row[0] for row in guard_query]
    live_room_info = await AsyncMySQL.execute(
        "select short_room_id, real_room_id from biliuser where real_room_id in %s;",
        (room_id_list, )
    )
    real_to_short_dict = {row[1]: row[0] for row in live_room_info}

    gifts = {}
    for row in guard_query:
        room_id, gift_name = row
        gifts.setdefault(room_id, []).append(gift_name)

    guard_list = []
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

        guard_list.append({
            "room_id": real_to_short_dict.get(room_id, room_id),
            "prompt": "、".join(display),
            "intimacy": intimacy
        })
    guard_list.sort(key=lambda x: (x["intimacy"], -x["room_id"]), reverse=True)

    context = {"guard_list": guard_list, "update_time": str(datetime.datetime.now())[:19]}
    return jinja2.Template(template_text).render(context)


async def main():
    intro = await gen_intro()
    obj = await DBCookieOperator.get_by_uid(user_id="DD")
    r = await BiliApi.update_brief_intro(cookie=obj.cookie, description=intro)
    print(r)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
