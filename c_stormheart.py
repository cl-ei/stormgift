import asyncio
from crontab_task.stormheart import main


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
