import logging
import random
import re

import asks
import curio
from asks.response_objects import Response
from curious import EventContext, Message, event
from curious.commands import Plugin, command, Context

from jokusoramame import USER_AGENT
from jokusoramame.utils import get_apikeys, is_owner

ISSUE_REGEXP = re.compile(r"(\S+)/(\S+)#([0-9]+)")
logger = logging.getLogger(__file__)


class Fuyu(Plugin):
    """
    Plugin for my server.
    """
    API_URL = "https://api.github.com"
    HEADERS = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": USER_AGENT,
    }

    def __init__(self, client):
        super().__init__(client)

        self.githubkey = get_apikeys("github")

    @command()
    @is_owner()  # Good enough for now...
    async def massnick(self, ctx: Context, prefix: str = '', suffix: str = ''):
        good = 0
        bad = 0

        for member in ctx.guild.members.values():
            task = await curio.spawn(member.nickname.set(prefix + member.user.username + suffix), report_crash=False)
            try:
                await task.join()
            except curio.TaskError:
                bad += 1
            else:
                good += 1

        await ctx.channel.messages.send(f"Tried changing {good + bad} nicknames. ({good} successful, {bad} failed.)")

    @event("message_create")
    async def annoy(self, ctx: EventContext, message: Message):
        if message.channel.id != 353878396670836736:
            return

        if message.author.guild_permissions.manage_messages:
            return

        chance = random.randint(0, 2)
        if chance == 1:
            await message.delete()
        else:
            if message.author.id == ctx.bot.user.id:
                return

            await message.channel.messages.send(message.author.mention)

    @event("message_create")
    async def link_issue(self, ctx: EventContext, message: Message):
        """
        Links an issue in my channel.
        """
        gh_token = self.githubkey.key
        headers = {"Authorization": f"Token {gh_token}", **self.HEADERS}

        if message.guild_id != 198101180180594688:
            return

        match = ISSUE_REGEXP.match(message.content)
        if not match:
            return

        owner, repo, issue = match.groups()
        url = self.API_URL + f"/repos/{owner}/{repo}/issues/{issue}"
        request: Response = await asks.get(headers=headers, uri=url)
        if request.status_code == 429:  # rate-limit
            return

        elif request.status_code == 404:  # unknown issue
            return await message.channel.messages.send(":x: Issue does not exist.")

        elif request.status_code == 200:  # valid
            data = request.json()
            issue_url = data["html_url"]
            return await message.channel.messages.send(issue_url)

        else:
            logger.warning(f"Got status code {request.status_code} from GitHub...\n"
                           f"{request.content}")
