"""
Misc utilities.
"""
# create the asyncio event loop
import asyncio
import json
from typing import Any, List, Sequence, Tuple

from dataclasses import dataclass

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


@dataclass
class APIKey(object):
    #: The actual API key.
    key: str

    #: For services that require it, the API ID.
    id_: str = None


def get_apikeys(name: str) -> APIKey:
    """
    Gets API keys for the specified name.

    :param name: The name of the API keys to load.
    :return:
    """
    with open(f"apikeys/{name}.json") as f:
        data = json.load(f)

    if 'id' in data:
        data['id_'] = data.pop('id')

    data.pop("_comment", None)

    return APIKey(**data)


def chunked(sequence: Sequence[Any], chunk_size: int):
    """
    Splits a sequence into sized chunks

    :param sequence: The sequence to be chunked.
    :param chunk_size: Amount of items per chunk.
    """
    for i in range(0, len(sequence), chunk_size):
        yield sequence[i:i + chunk_size]
