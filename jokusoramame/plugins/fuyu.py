import asks
import curio
import logging
import random
import re
from asks.response_objects import Response
from curious import EventContext, Message, event
from curious.commands import Context, Plugin, command
from fractions import Fraction

from jokusoramame import USER_AGENT
from jokusoramame.utils import get_apikeys, is_owner

ISSUE_REGEXP = re.compile(r"(\S+)/(\S+)#([0-9]+)")
logger = logging.getLogger(__file__)


class AverageOverTime:
    def __init__(self):
        self.count = 0
        self.items = []

    def __iadd__(self, item):
        self.count += 1
        self.items.append(item)
        return self

    def __iter__(self):
        yield from self.items

    @property
    def average(self):
        return sum(self.items) / self.count


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

        self.averager = AverageOverTime()

    @command()
    async def yert(self, ctx: Context):
        """
        :yert:
        """
        n = random.choices(range(1, 76), (x ** 1.5 for x in range(75, 0, -1)))[0]
        self.averager += n
        await ctx.channel.messages.send('<:yert:392393965233504266>' * n)

    @yert.subcommand()
    async def stats(self, ctx: Context):
        """
        Shows statistics about the results of the yert command
        """
        whole_part = int(self.averager.average)
        fraction = Fraction(self.averager.average - whole_part)
        approx = fraction.limit_denominator(50)
        num = f'{whole_part} ' + str(approx) * bool(approx)
        await ctx.channel.messages.send(f'Average <:yert:392393965233504266>s: {num}\n'
                                        f'Max <:yert:392393965233504266>s this session: '
                                        f'{max(self.averager)}')

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

        await ctx.channel.messages.send(f"Tried changing {good + bad} nicknames. "
                                        f"({good} successful, {bad} failed.)")

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

    @event("message_create")
    async def is_that_sans_undertale(self, ctx: EventContext, message: Message):
        """
        Is that Sans Undertale?
        """
        return

        if message.guild_id != 198101180180594688:
            return

        if message.author_id != 95473026350452736:
            return

        if len(message.attachments) <= 0:
            return

        messages = [
            "Is that Sans the skeleton from Undertale?",
            "Is that Sans undertale?",
            "Is that Sans from Undertale?",
            "Is that Ness the skeleton from Undertale?",
        ]

        await message.channel.messages.send(random.choice(messages))
