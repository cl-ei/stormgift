import os
import sys
import time
import json
import asyncio
import aiohttp
import weakref
import datetime
from random import choice
from aiohttp import web

if sys.platform.lower() == "linux":
    DEBUG = False
else:
    DEBUG = True

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

music_files = os.listdir("./live_room_statics/music/")
image_files = os.listdir("./live_room_statics/img/")


class MusicList:
    background_musics = ["/static/music/" + mp3 for mp3 in music_files]
    music_list = [
        # ("music_name", "user")
    ]

    last_change_song_time = time.time()


async def get_song_param(song_name):
    req_params = {
        "method": "post",
        "url": "http://music.163.com/api/search/pc",
        "headers": headers,
        "data": {"s": song_name, "type": 1, "limit": 50, "offset": 0},
    }

    async with aiohttp.request(**req_params) as response:
        status_code = response.status
        if status_code != 200:
            return False, f"{song_name} 请求错误"
        content = await response.text()

    songs = json.loads(content).get("result", {}).get("songs", []) or []
    if not isinstance(songs, list):
        return False, f"{song_name} 请求错误"

    song_name = song_name.lower().strip()
    for song in songs:
        name = song.get("name").lower().strip()
        if (
                name == song_name
                or (len(name) < len(song_name) and name in song_name)
                or (len(song_name) < len(name) and song_name in name)
        ):
            return True, song
    return True, songs[0]


async def download_song(song_id, song_name):
    try:
        path = f"./live_room_statics/download/{song_name}.lrc"
        if not os.path.exists(path):
            lyric = None
            lyc_url = f"http://music.163.com/api/song/media?id={song_id}"
            async with aiohttp.request("get", headers=headers, url=lyc_url) as r:
                if r.status == 200:
                    response = json.loads(await r.text())
                    lyric = response.get("lyric") or ""
            if not lyric:
                raise Exception("No lyric!")
            with open(path, "w") as f:
                f.write(lyric)
                print(f"lrc download success: {song_name} -> {len(lyric)}")
    except Exception as e:
        print(f"Lyric download error: {e}")

    path = f"./live_room_statics/download/{song_name}.mp3"
    if os.path.isfile(path):
        return True, ""

    url = f"http://music.163.com/song/media/outer/url?id={song_id}.mp3"
    cmd = f"wget -O {path} \"{url}\""
    download_info = os.popen(cmd).read()
    print(f"download_info: {download_info}")
    return True, download_info


async def main():
    command_q = asyncio.Queue()

    app = web.Application()
    app['ws'] = weakref.WeakSet()

    async def home_page(request):
        with open("music.html", encoding="utf-8") as f:
            from jinja2 import Template
            music_html = f.read()
            template = Template(music_html)

        context = {
            "DEBUG": DEBUG,
            "CDN_URL": "http://192.168.100.100:80",
            "title": "grafana",
            "background_images": ["/static/img/" + img for img in image_files],
            "background_musics": ["/static/music/" + mp3 for mp3 in music_files],
        }

        return web.Response(text=template.render(context), content_type="text/html")

    async def notice(data):
        data["cmd"] = "update"
        for ws in set(app['ws']):
            await ws.send_str(json.dumps(data, ensure_ascii=False))

    async def flush_player():
        if MusicList.music_list:
            current = MusicList.music_list[0][0]
            extra = f"来自{MusicList.music_list[0][1]}的点播。接下来播放："
            play_list = [x[0] for x in MusicList.music_list[1:]] or ["无"]
        else:
            current = choice(MusicList.background_musics)
            extra = f"接下来播放："
            play_list = ["无"]

        message = {
            "current": current,
            "extra": extra,
            "play_list": play_list,
        }

        def parse_lyrics(lyric):
            result = []
            for line in lyric.split("\n"):
                try:
                    if "[" not in line or "]" not in line:
                        continue

                    time_str, lyric = line.split("[")[1].split("]", 1)
                    lyric = lyric.split("]")[-1].strip()

                    minute, seconds = time_str.split(":")
                    time_line = int(minute.lstrip("0") or "0")*60 + float(seconds)
                    result.append([time_line, lyric])
                except Exception as e:
                    print(f"parse_lyrics Exception: {e}")
                    continue

            return result

        song_name = current.split("/")[-1].split(".")[0]
        path = f"./live_room_statics/download/{song_name}.lrc"
        try:
            with open(path, "r") as f:
                message["lyric"] = parse_lyrics(f.read())
        except IOError:
            pass
        await notice(message)

    async def command(request):
        cmd = request.match_info['cmd']
        user, song = cmd.split("$", 1)
        command_q.put_nowait((user, song))
        await notice({"prompt": f"收到{user}的点歌指令: {song}"})
        return web.Response(status=206)

    async def ws_server(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        request.app['ws'].add(ws)
        try:
            async for msg in ws:
                if msg.data in ("next", "init"):
                    if MusicList.music_list and msg.data == "next":
                        MusicList.music_list.pop(0)

                    MusicList.last_change_song_time = time.time()
                    await flush_player()
        finally:
            request.app['ws'].discard(ws)
        return ws

    app.add_routes([
        web.get('/', home_page),
        web.get('/command/{cmd}', command),
        web.get('/ws', ws_server),
        web.static('/static', "./live_room_statics")
    ])
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', 4096)
    await site.start()
    print("Site started.\nhttp://127.0.0.1:4096")

    async def proc_song():
        while True:
            user, song = await command_q.get()
            if len(MusicList.music_list) > 6:
                await notice({"prompt": f"歌单已满，请稍后点歌。点歌格式：点歌 出山"})
                continue

            flag, song_param = await get_song_param(song)
            if not flag:
                await notice({"prompt": f"未找到歌曲：{song}"})
                await asyncio.sleep(3)
                continue

            song = song_param.get("name", "??")
            song_id = song_param["id"]

            if song in [x[0] for x in MusicList.music_list]:
                await notice({
                    "prompt": "下载完毕。点歌格式：点歌 出山",
                    "play_list": [x[0] for x in MusicList.music_list[1:]] or ["无"],
                })
                continue

            await notice({"prompt": f"开始下载：{song}"})
            flag, msg = await download_song(song_id, song)
            if not flag:
                await notice({"prompt": f"{song} 下载出错！"})
                await asyncio.sleep(3)
                continue

            MusicList.music_list.append((f"/static/download/{song}.mp3", user))
            await notice({
                "prompt": "下载完毕。点歌格式：点歌 出山",
                "play_list": [x[0] for x in MusicList.music_list[1:]] or ["无"],
            })
            # 如果队列里只有1首，那么立即播放
            if len(MusicList.music_list) == 1:
                await flush_player()

    async def monitor_song():
        while True:
            await asyncio.sleep(1)
            if time.time() - MusicList.last_change_song_time > 300:
                if MusicList.music_list:
                    s = MusicList.music_list.pop(0)
                    print(f"Force pop: {s}")
                else:
                    print("Too long! Force change song.")
                MusicList.last_change_song_time = time.time()
                await flush_player()

    await asyncio.gather(proc_song(), monitor_song())


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
