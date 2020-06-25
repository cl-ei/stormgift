import jinja2
import asyncio
import requests
import datetime
from utils.biliapi import BiliApi
from db.queries import queries, LTUser


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
    href="https://jq.qq.com/?_wv=1027&k=5dO3qQY">
    加入宝藏站点交流群:614382552
  </a>
</span>
</div>

<div style="border-bottom: 1px dashed #ccc;">
  <p style="margin-top: 0px">ヾ(❀╹◡╹)ﾉﾞ❀~&nbsp; 点此去
    <a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
      href="https://www.madliar.com/bili/guards" target="_blank">
      礼物列表站点
    </a>
    <span>，</span>
    <a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
      href="https://www.madliar.com/bili/broadcast" target="_blank">
      实时广播站（WS协议）
    </a>
  </p>
  <p>想看看都谁中奖了？➟ 
    <a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
      href="https://www.madliar.com/bili/raffles" target="_blank">获奖记录</a>
    <br />  
    收藏歌单？➟
    <a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;" 
      href="https://www.madliar.com/music" target="_blank">音乐列表</a>
    <br />
    交流群➟ <a style="padding: 0px;color: #7a91f3;border-bottom: 1px solid;padding-bottom: 2px;"
    href="https://jq.qq.com/?_wv=1027&k=5dO3qQY">614 382 552</a>
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
    context = requests.get("https://www.madliar.com/bili/realtime_guards").json()
    return jinja2.Template(template_text).render(context)


async def main():
    intro = await gen_intro()
    lt_user: LTUser = await queries.get_lt_user_by_uid(user_id="DD")
    r = await BiliApi.update_brief_intro(cookie=lt_user.cookie, description=intro)
    print(r)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
