import asyncio
from core import Core


loop = asyncio.get_event_loop()
loop.run_until_complete(Core().run())
