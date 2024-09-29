import asyncio
import aiohttp
import sys



from runner import configure

from loguru import logger
from .agent import agent as aigf_agent

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def main():
    async with aiohttp.ClientSession() as session:
        (url, token, participant_id) = await configure(session)
        await aigf_agent(url, token, participant_id)
        

if __name__ == "__main__":
    asyncio.run(main())