"""
Misc utilities.
"""
# create the asyncio event loop
import asyncio

try:
    import uvloop

    print("Using uvloop")
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    try:
        import tokio
        print("Using Tokio")
        asyncio.set_event_loop_policy(tokio.EventLoopPolicy())
    except ImportError:
        print("Using vanilla asyncio")
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

from curio import AsyncioLoop

# create the asyncio bridge
loop = AsyncioLoop(event_loop=asyncio.get_event_loop())
