"""
Jokusoramame - a terrible discord bot.
"""
import aiohttp
import re

__author__ = "Isaac Dickinson"

VERSION = "0.3.0"
VERSIONT = tuple(map(int, VERSION.split(".")))

version_matcher = re.compile(r'VERSION = "(.*)"')

async def get_version():
    with aiohttp.ClientSession() as sess:
        async with sess.get("https://raw.githubusercontent.com/SunDwarf/Jokusoramame/master/joku/__init__.py") as r:
            assert isinstance(r, aiohttp.ClientResponse)
            data = await r.read()
            vers = version_matcher.match(data)

            try:
                return vers.groups()[0]
            except IndexError:
                return None

async def compare_versions():
    vers = await get_version()
    if not vers:
        return -2

    vers = tuple(map(int, vers.split()))

    if vers > VERSIONT:
        return 1
    elif vers < VERSIONT:
        return -1
    else:
        return 0
