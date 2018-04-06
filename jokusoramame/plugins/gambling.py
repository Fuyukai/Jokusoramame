# TODO
# - item system
#   - store
#   - use
#   - inventory

import random
from collections import namedtuple
from typing import List

import numpy as np
import tabulate
from curious import Embed, Guild, Member
from curious.commands import Context, Plugin, command
from curious.commands.decorators import ratelimit
from curious.ext.paginator import ReactionsPaginator

from jokusoramame.db.tables import UserBalance
from jokusoramame.utils import chunked

BAD_RESPONSES = [
    '\N{FIRE} Your bank account went up in flames and you lost **{0} :̶.̶|̶:̶;̶**.',
    '\N{SHOPPING TROLLEY} You spend **{0} :̶.̶|̶:̶;̶** at the supermarket.',
    '\N{GHOST} A ghost pops up out of nowhere and scares you. You drop **{0} :̶.̶|̶:̶;̶**.',
    '\N{HAMMER AND PICK} _All that is solid melts into air._ (You lost **{0} :̶.̶|̶:̶;̶**.)'
]

GOOD_RESPONSES = [
    '\N{FIRST PLACE MEDAL} You win first place in the Money Making Race™ and gain **{0} :̶.̶|̶:̶;̶**.',
    '\N{SLOT MACHINE} You have a gambling addiction and win **{0} :̶.̶|̶:̶;̶**.',
    '\N{GEM STONE} You find a diamond and sell it for **{0} :̶.̶|̶:̶;̶**.'
]


async def update_balance(ctx: Context, balance, amount: int):
    async with ctx.bot.db.get_session() as sess:
        balance.money += amount
        await sess.add(balance)


class Gambling(Plugin):
    """
    Plugin for gambling related commands.
    """

    async def ensure_balance(self, member: Member = None):
        """
        Return a balance associated to the member and corresponding guild. If one does not exist it is created.

        :param member: Member to ensure balance for.
        """
        async with self.client.db.get_session() as sess:
            balance = await sess.select.from_(UserBalance) \
                .where((UserBalance.user_id.eq(member.id)) & (UserBalance.guild_id.eq(member.guild.id))) \
                .first()

            if balance is None:
                balance = UserBalance()
                balance.guild_id = member.guild_id
                balance.user_id = member.id
                balance.money = 0
                await sess.add(balance)

            return balance

    async def construct_leaderboard(self, guild: Guild, *, mode: str) -> List[str]:
        """
        Query the database for the balance of each member in a guild, and sort it appropriately.

        A table follows this format:
        |   POS | User    |   Money |
        |-------+---------+---------|
        |     1 | name    |       0 |

        each table contains 10 entries

        :param guild: The guild to construct the leaderboard for.
        :param mode: Tells if the results should be ordered in ascending or descending order.
        :return: A list of formatted tables.
        """
        order_by = {
            'top': UserBalance.money.desc(),
            'bottom': UserBalance.money.asc()
        }

        async with self.client.db.get_session() as sess:
            query = sess.select(UserBalance) \
                .where(UserBalance.guild_id.eq(guild.id)) \
                .order_by(order_by[mode])

            rows = await query.all()
            rows = await rows.flatten()

        entry = namedtuple('entry', 'position name money')
        pages = []
        pos = 0

        for chunk in chunked(rows, 10):
            rows = []

            for row in chunk:
                pos += 1

                member = guild.members.get(row.user_id)
                name = member.user.name if member else str(row.user_id)

                # Strips unicode
                name = name.encode('ascii', errors='replace').decode()
                rows.append(entry(pos, name, row.money))

            tab = tabulate.tabulate(rows, headers='POS User Money'.split(), tablefmt='orgtbl')
            pages.append('```' + tab + '```')

        return pages

    @ratelimit(limit=5, time=3600)  # 5 per 1h
    @command()
    async def raffle(self, ctx: Context, price: int = 5):
        """
        Lady luck is smiling
        """
        balance = await self.ensure_balance(ctx.author)

        price = max(price, 5)  # No mercy for the "hahaha I am very sneaky" user

        if balance.money <= 0:
            # vintage
            await ctx.channel.messages.send(
                '\N{DRAGON} A debt collector came and broke your knees. '
                'You are now free of debt.'
            )
            await update_balance(ctx, balance, abs(balance.money) + 5)
            return

        if balance.money < price:
            return await ctx.channel.messages.send("\N{CROSS MARK} Don't gamble with money you don't have, dum-dum...")

        amount = int(((price * 10) * np.random.randn()) + price)  # weight slightly towards positive

        if amount < 0:
            response = random.choice(BAD_RESPONSES)
        else:
            response = random.choice(GOOD_RESPONSES)

        await ctx.channel.messages.send(response.format(abs(amount)))
        await update_balance(ctx, balance, amount)

    @ratelimit(limit=1, time=86_400)  # 24h
    @command()
    async def daily(self, ctx: Context):
        """
        Gives you a small amount of credits.
        """
        amount = 1 + np.random.exponential()
        # Rounds to nearest 5
        amount = int(5 * round(amount * 50 / 5))

        await ctx.channel.messages.send(f'\N{MONEY BAG} You have earned **{amount} :̶.̶|̶:̶;̶** today.')
        await update_balance(ctx, await self.ensure_balance(ctx.author), amount)

    @command()
    async def richest(self, ctx: Context):
        """
        Shows the people with the most amount of money in a guild.
        """
        pages = await self.construct_leaderboard(ctx.guild, mode='top')

        if not pages:
            return await ctx.channel.messages.send('\N{CROSS MARK} No entries found for this guild.')

        paginator = ReactionsPaginator(content=pages, channel=ctx.channel, respond_to=ctx.author)
        await paginator.paginate()

    @command()
    async def poorest(self, ctx: Context):
        """
        Shows the people with the least amount of money in a guild.
        """
        pages = await self.construct_leaderboard(ctx.guild, mode='bottom')

        if not pages:
            return await ctx.channel.messages.send('\N{CROSS MARK} No entries found for this guild.')

        paginator = ReactionsPaginator(content=pages, channel=ctx.channel, respond_to=ctx.author)
        await paginator.paginate()

    @command()
    async def balance(self, ctx: Context, *, target: Member = None):
        """
        Gets the current amount of money a person has.
        """
        if target is None:
            target = ctx.author

        if target.user.bot:
            return await ctx.channel.messages.send('\N{CROSS MARK} Bots cannot earn money.')

        balance = await self.ensure_balance(target)

        embed = Embed(title=str(target.name), colour=target.colour)
        embed.set_thumbnail(url=str(target.user.avatar_url))
        embed.add_field(name='Balance', value=f'**{balance.money} :̶.̶|̶:̶;̶**')

        await ctx.channel.send(embed=embed)
