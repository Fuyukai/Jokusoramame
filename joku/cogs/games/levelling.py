"""
cancer
"""
from io import BytesIO
from math import floor, ceil

import discord
from asyncio_extras import threadpool
from discord.ext import commands

import matplotlib as mpl
mpl.use('Agg')

import matplotlib.pyplot as plt
import numpy as np
from numpy.polynomial import Polynomial as P
import seaborn as sns

from joku.bot import Jokusoramame, Context
from joku.db.tables import User
from joku.cogs._common import Cog
from joku.utils import paginate_table, reject_outliers


INCREASING_FACTOR = 50


def get_level_from_exp(xp: int, a: int = INCREASING_FACTOR) -> int:
    """
    Gets the level from the experience number.

    U(n) = a* (n*(n+1)  / 2), a ∈ ℝ, a > 0
    :param a: The levelling up constant.
    :param xp: The XP this user currently has.
    """
    # Make sure XP is below INCREASING_FACTOR.
    if xp < a:
        # Level 1
        return 1

    # The equation that we need to solve is (a/2)n**2 + (a/2)n - xp = 0.
    # So we get numpy to find our roots.
    ab = a / 2
    # C, B, A
    to_solve = [-xp, ab, ab]
    poly = P(to_solve)

    # Positive root + 1
    root = poly.roots()[1] + 1
    return int(floor(root))


def get_next_exp_required(xp: int, a: int = INCREASING_FACTOR):
    """
    Gets the EXP required for the next level, based on the current EXP.

    :param a: The levelling up constant.
    :param xp: The XP this user currently has.
    :return: The amount of XP required for the next level, and the current level.
    """
    # No complxes
    if xp < a:
        return 1, a - xp

    # Solve the current level.
    current_level = get_level_from_exp(xp, a)

    # Substitute in (n+1) to a* (n*(n+1)  / 2), where n == current_level
    # or not idk
    exp_required = int(a * (current_level * (current_level + 1) / 2))

    return current_level, exp_required - xp


class Levelling(Cog):
    async def on_message(self, message: discord.Message):
        # Add XP, and show if they levelled up.
        if message.author.bot:
            return

        # No discord bots, thanks.
        if message.guild.id == 110373943822540800:
            return

        # Check the spam quotient.
        if not await self.bot.redis.prevent_spam(message.author):
            # The user said more than 15 messages in the last 60 seconds, so don't add XP.
            return

        # Check if this channel should be ignored for levelling.
        #if await self.bot.database.is_channel_ignored(message.channel, type_="levels"):
        #    return

        user = await self.bot.database.update_user_xp(message.author)
        # Get the level.
        new_level = get_level_from_exp(user.xp)

        if user.level < new_level:
            user = await self.bot.database.set_user_level(message.author, new_level)

            all_users = await self.bot.database.get_multiple_users(*message.guild.members, order_by=User.xp.desc())
            index, u = next(filter(lambda j: j[1].id == message.author.id, enumerate(all_users)))

            if message.channel.permissions_for(message.guild.me).embed_links:
                em = discord.Embed(title="Level up!")
                em.description = "**{} is now level {}!** " \
                                 "Current XP: {}".format(message.author.name, new_level, user.xp)

                xp = user.xp
                required = get_next_exp_required(xp)[1]
                em.add_field(name="Required for next level", value="{} XP".format(required))
                em.add_field(name="Rank", value="{} / {}".format(index + 1, len(all_users)))

                em.colour = discord.Colour.green()
                em.set_thumbnail(url=message.author.avatar_url)

                await message.channel.send(embed=em)
            else:
                await message.channel.send(":up: **{} is now level {}!**".format(message.author, user["level"]))

    @commands.group(pass_context=True, invoke_without_command=True)
    async def level(self, ctx: Context, *, target: discord.Member = None):
        """
        Shows the current level for somebody.

        If no user is passed, this will show your level.
        """
        user = target or ctx.message.author
        if user == ctx.guild.me:
            await ctx.send(":100: I am level infinity.")
            return

        if user.bot:
            await ctx.channel.send(":no_entry_sign: **Bots cannot have XP.**")
            return

        all_users = await ctx.bot.database.get_multiple_users(*ctx.message.guild.members, order_by=User.xp.desc())

        index, u = next(filter(lambda j: j[1].id == user.id, enumerate(all_users)))

        embed = discord.Embed(title=user.nick or user.name)
        embed.set_thumbnail(url=user.avatar_url)

        embed.add_field(name="Level", value=str(u.level))
        embed.add_field(name="Rank", value="{} / {}".format(index + 1, len(all_users)))
        embed.add_field(name="XP", value=str(u.xp))
        required = get_next_exp_required(u.xp)[1]

        embed.add_field(name="XP required for next level", value=required)
        embed.colour = user.colour

        await ctx.channel.send(embed=embed)

    @level.command(pass_context=True, aliases=["top"])
    async def leaderboard(self, ctx: Context, *, num: int = 10):
        """
        Shows the top 10 people in this server.

        This uses the global XP counter.
        """
        users = await ctx.bot.database.get_multiple_users(*ctx.message.guild.members, order_by=User.xp.desc())

        base = "**Top {} users (in this server):**\n\n".format(num)

        # Create a table using tabulate.
        headers = ["POS", "User", "XP", "Level"]
        table = []

        for n, u in enumerate(users[:num]):
            try:
                member = ctx.message.guild.get_member(u.id).name
                # Unicode and tables suck
                member = member.encode("ascii", errors="replace").decode()
            except AttributeError:
                # Prevent race condition - member leaving between command invocation and here
                continue
            # position, name, xp, level
            table.append([n + 1, member, u.xp, u.level])

        # Format the table.
        pages = paginate_table(table, headers)

        await ctx.channel.send(base)
        for page in pages:
            await ctx.channel.send(page)

    @level.command(pass_context=True, aliases=['graph'])
    async def plot(self, ctx: Context):
        """
        Plots the XP curve for this server.
        """
        if ctx.author.id == 133139430495092737:
            await ctx.send(":x: Fuck you")
            return

        users = await ctx.bot.database.get_multiple_users(*ctx.message.guild.members, order_by=User.xp.desc())

        async with ctx.channel.typing():
            async with threadpool():
                _lvls = np.array([user.level for user in users if user.level >= 0])
                lvls = reject_outliers(_lvls, m=1)

                # This changes the line/shade colour apparently.
                sns.set_palette(['#DFA5A4'])
                sns.set_style('white')

                # The bw argument makes it slightly less "rounded"
                ax = sns.kdeplot(lvls, shade=True, bw=0.3)

                plt.xlabel('Level', fontsize=14)
                plt.title('Level distribution curve for {}'.format(ctx.message.guild.name),
                          fontsize=23)

                # Remove text from left
                plt.yticks([])

                # "Hacky" way of limiting the x-axis but I couldnt
                # come up with anything better
                max_level = ceil(max(lvls) / 10) * 10
                plt.xticks(np.arange(0, max_level, 10))

                # Set the limits of the axis so it doesnt
                # expand too much in any direction
                ax.set_xbound(0, max_level + 1)

                # Removes the spines
                sns.despine()
                ax.spines['bottom'].set_visible(False)
                ax.spines['left'].set_visible(False)

                buf = BytesIO()
                plt.savefig(buf, format="png")

                # Don't send 0-byte files
                buf.seek(0)

                # Cleanup.
                plt.clf()
                plt.cla()

        await ctx.channel.send(file=buf, filename="plot.png")

    @level.command(pass_context=True)
    async def next(self, ctx, *, target: discord.Member = None):
        """
        Shows the next level for somebody.

        If no user is passed, this will show yours.
        """
        user = target or ctx.message.author
        if user.bot:
            await ctx.channel.send(":no_entry_sign: **Bots cannot have XP.**")
            return

        xp = (await ctx.bot.database.get_or_create_user(user)).xp

        level, exp_required = get_next_exp_required(xp)

        await ctx.channel.send("**{}** needs `{}` XP to advance to level `{}`.".format(user.name, exp_required,
                                                                                       level + 1))

    @commands.command(pass_context=True, aliases=["exp"])
    async def xp(self, ctx, *, target: discord.Member = None):
        """
        Shows the current XP for somebody.

        If no user is passed, this will show your XP.
        """
        user = target or ctx.message.author
        if user.bot:
            await ctx.channel.send(":no_entry_sign: **Bots cannot have XP.**")
            return

        exp = (await ctx.bot.database.get_or_create_user(user)).xp

        await ctx.channel.send("User **{}** has `{}` XP.".format(user.name, exp))


def setup(bot: Jokusoramame):
    bot.add_cog(Levelling(bot))
