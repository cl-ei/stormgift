import asyncio
from utils import core


loop = asyncio.get_event_loop()
loop.run_until_complete(core.run_forever())
loop.run_forever()
