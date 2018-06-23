"""
Plugin and utilities for levelling.
"""
import random
import tabulate
from asyncqlio import Session
from curious import Embed, EventContext, Member, Message, event
from curious.commands import Context, Plugin, command
from curious.exc import Forbidden, PermissionsError
from curious.ext.paginator import ReactionsPaginator
from numpy.ma import floor
from numpy.polynomial import Polynomial as P
from typing import List

from jokusoramame.db.tables import UserXP
from jokusoramame.utils import chunked

INCREASING_FACTOR = 75


def get_level_from_exp(xp: int, a: int = INCREASING_FACTOR) -> int:
    """
    Gets the level from the experience number.

    U(n) = a* (n*(n+1)  / 2), a ∈ ℝ, a > 0

    :param xp: The XP this user currently has.
    :param a: The levelling up constant.
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
    :return: The current level, and the amount of XP required for the next level.
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


class Levelling(Plugin):
    """
    Plugin for levelling.
    """

    @event("message_create")
    async def update_levels(self, ctx: EventContext, message: Message):
        """
        Handles updating levels.
        """
        # no dms
        if message.guild is None:
            return

        # no bots!
        if message.author.user.bot:
            return

        # TODO: Handle anti-spam.
        # first, get the amount of XP we're gonna add
        xp_add = random.randint(0, 4)
        if xp_add == 0:
            return

        sess: Session = ctx.bot.db.get_session()
        async with sess:
            # results = await sess.execute("""
            # SELECT * FROM (SELECT rank() OVER(ORDER BY xp DESC), user_xp.* FROM user_xp WHERE
            # guild_id = ) t WHERE t.user_id = :user_id;
            # """)

            # TODO: Move this into the database.
            users = await sess.select(UserXP) \
                .where(UserXP.guild_id.eq(message.guild_id)) \
                .order_by(UserXP.xp.desc()) \
                .all()
            users: List[UserXP] = await users.flatten()

            index, user = next(
                filter(lambda tup: tup[1].user_id == message.author_id, enumerate(users)),
                (None, None)
            )

            if user is None:
                user = UserXP()
                user.guild_id = message.guild_id
                user.user_id = message.author_id
                user.level = 1
                user.xp = 0

            # add on the xp
            user.xp += xp_add
            # check if the user can level up
            next_level = get_level_from_exp(user.xp)
            try:
                if next_level > user.level:
                    user.level = next_level

                    # make the embed to send
                    em = Embed()
                    em.title = "Level up!"
                    em.description = f":tada: **{message.author.user.username} is now level " \
                                     f"{user.level}!** Current XP: {user.xp} XP"
                    em.set_thumbnail(url=message.author.user.static_avatar_url)
                    em.colour = message.author.colour
                    # calculatte required xp
                    level, required = get_next_exp_required(user.xp)
                    em.add_field(name=f"Required for level {level + 1}", value=f"{required} XP")
                    em.add_field(name="Ranking",
                                 value=f"{index + 1 if index is not None else '???'} "
                                       f"/ {len(users)}")
                    # get ranking
                    # ranking, total = await ctx.bot.db.get_userxp_ranking(message.author)
                    # em.add_field(name="Ranking", value=f"{ranking} / {total}")

                    try:
                        await message.channel.messages.send(embed=em)
                    except (PermissionsError, Forbidden):
                        # no embeds
                        try:
                            await message.channel.messages.send(f":tada: "
                                                                f"**{message.author.user.username} "
                                                                f"is now level {user.level}**!")
                        except (PermissionsError, Forbidden):
                            # oh well
                            pass
            finally:
                await sess.add(user)

    @command()
    async def level(self, ctx: Context, *, member=None):
        """
        Shows the level of somebody, or yourself.
        """
        # default member is the author
        if member in ["top", "bottom"]:
            return await self.leaderboard(ctx, mode=member)

        if member is not None:
            member = ctx._lookup_converter(Member)(Member, ctx, member)
        member = member or ctx.author

        sess: Session = ctx.bot.db.get_session()
        async with sess:
            # TODO: Move this into the database.
            users = await sess.select(UserXP) \
                .where(UserXP.guild_id.eq(member.guild_id)) \
                .order_by(UserXP.xp.desc()) \
                .all()

            users: List[UserXP] = await users.flatten()

            filtered = filter(lambda tup: tup[1].user_id == member.id, enumerate(users))
            index, user = next(filtered, (None, None))

        if user is None:
            await ctx.channel.send(f"{member.mention} has no level data.")
            return

        em = Embed()
        em.title = str(member.nickname)
        em.add_field(name="Level", value=user.level, inline=True)
        em.add_field(name="XP", value=user.xp)
        em.add_field(name="XP required for next level", value=str(get_next_exp_required(user.xp)[1]))
        em.add_field(name="Ranking", value=f"{index + 1} / {len(users)}")
        em.colour = member.colour
        em.thumbnail.url = member.user.static_avatar_url
        await ctx.channel.send(embed=em)

    @level.subcommand()
    async def leaderboard(self, ctx: Context, *, mode: str = "top"):
        """
        Shows the current leaderboard for levels.
        """
        sess: Session = ctx.bot.db.get_session()
        async with sess:
            query = sess.select(UserXP).where(UserXP.guild_id.eq(ctx.guild.id))
            if mode == "bottom":
                query = query.order_by(UserXP.xp.asc())
            else:
                query = query.order_by(UserXP.xp.desc())
            rows = await query.all()
            rows: List[UserXP] = await rows.flatten()

        # paginate into chunks
        messages = []
        position = 0
        for chunk in chunked(rows, 10):
            rows = []

            for row in chunk:
                position += 1
                member = ctx.guild.members.get(row.user_id)
                name = member.user.name if member is not None else str(row.user_id)
                # no unicode tyvm
                name = name.encode("ascii", errors="replace").decode("ascii", errors="replace")
                rows.append((str(position), name, row.xp, row.level))

            tbl = tabulate.tabulate(rows, headers=["POS", "User", "XP", "Level"],
                                    tablefmt="orgtbl")

            messages.append(f"```\n{tbl}```")

        if len(messages) == 1:
            return await ctx.channel.send(messages[0])

        if not ctx.channel.me_permissions.add_reactions:
            for message in messages:
                await ctx.channel.messages.send(message)
        else:
            paginator = ReactionsPaginator(content=messages, channel=ctx.channel, respond_to=ctx.author)
            await paginator.paginate()

    @level.subcommand(name="next")
    async def next_(self, ctx: Context, target: Member = None):
        """
        Shows the amount of XP required to level up for a target (defaults to yourself).
        """
        if target is None:
            target = ctx.author

        sess: Session = ctx.bot.db.get_session()
        async with sess:
            row: UserXP = await sess.select.from_(UserXP) \
                .where((UserXP.user_id == target.id) & (UserXP.guild_id == target.guild_id)) \
                .first()

        xp = row.xp if row is not None else 0
        _, xp_required = get_next_exp_required(xp)
        await ctx.channel.send(f"**{target.user.username}** needs `{xp_required}` XP to advance "
                               f"to level `{_ + 1}`.")

    @command()
    async def xp(self, ctx: Context, target: Member = None):
        """
        Shows the XP of a target (defaults to yourself).
        """
        if target is None:
            target = ctx.author

        sess: Session = ctx.bot.db.get_session()
        async with sess:
            row: UserXP = await sess.select.from_(UserXP) \
                .where((UserXP.user_id == target.id) & (UserXP.guild_id == target.guild_id)) \
                .first()

        if row is None:
            xp = 0
        else:
            xp = row.xp

        await ctx.channel.send(f"User **{target.user.username}** has `{xp}` XP.")
