from aiohttp import web


async def sms(request):
    r = await request.text()
    print(f"Request: {r}")
    return web.Response(text=f"OK")
