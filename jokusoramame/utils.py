"""
Misc utilities.
"""
# create the asyncio event loop
import asyncio
import json
from typing import List, Tuple

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


def rgbize(palette: List[int]) -> List[Tuple[float, float, float]]:
    """
    RGBizes a palette.
    """
    pal_colours = []
    for colour in palette:
        rgb255 = ((colour >> 16) & 255, (colour >> 8) & 255, colour & 255)
        rgb100 = tuple(c / 255 for c in rgb255)
        pal_colours.append(rgb100)

    return pal_colours


def get_apikeys(name: str) -> dict:
    """
    Gets the API keys for the specified name.
    """
    with open(f"apikeys/{name}.json") as f:
        return json.load(f)
