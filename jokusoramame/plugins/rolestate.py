from typing import List

import operator
from asyncqlio import Session
from curious import Member, EventContext, event, Embed, Guild, Role
from curious.commands import Plugin, Context, command
from curious.exc import NotFound

from jokusoramame.db.tables import Rolestate as tbl_rolestate
from jokusoramame.db.tables import GuildSetting as tbl_gsetting


class Rolestate(Plugin):
    """
    Plugin for rolestate.
    """

    async def add_rolestate(self, member: Member):
        """
        Adds rolestate for a user to the database.

        :param member: The :class:`.Member` object to add rolestate for.
        :return:
        """
        rolestate = tbl_rolestate(user_id=member.id, guild_id=member.guild_id,
                                  nick=str(member.nickname) if member.nickname else None,
                                  roles=",".join(map(str, member.role_ids)))

        sess: Session = self.client.db.get_session()
        async with sess:
            role = await sess.select(tbl_rolestate) \
                .where(tbl_rolestate.guild_id.eq(member.guild_id) &
                       tbl_rolestate.user_id.eq(member.id)) \
                .first()

            if role is None:
                await sess.insert.rows(rolestate).run()
            else:
                rolestate.id = role.id
                await sess.merge(rolestate)

        return rolestate

    def _unmap_rolestate(self, guild: Guild, rolestate_str: str) -> List[Role]:
        """
        Unmaps a list of roles into role objects.

        :param guild: The :class:`.Guild` containing the roles.
        :param rolestate_str: The comma-separated list of role IDs to get.
        """
        roles = []
        for i in rolestate_str.split(","):
            role = guild.roles.get(int(i))
            if role:
                roles.append(role)

        return roles

    @event("guild_member_remove")
    async def update_rolestate(self, ctx: EventContext, member: Member):
        """
        Updates the rolestate for a member.
        """
        await self.add_rolestate(member)

    @event("guild_member_add")
    async def readd_rolestate(self, ctx: EventContext, member: Member):
        """
        Re-adds rolestate to a user.
        """
        sess: Session = ctx.bot.db.get_session()
        async with sess:
            rolestate: tbl_rolestate = await sess.select(tbl_rolestate) \
                .where(tbl_rolestate.guild_id.eq(member.guild_id) &
                       tbl_rolestate.user_id.eq(member.user.id)) \
                .first()

            if not rolestate:
                return

            setting: tbl_gsetting = await sess.select(tbl_gsetting) \
                .where(tbl_gsetting.guild_id == member.guild_id) \
                .where(tbl_gsetting.name == "rolestate") \
                .first()

            if setting is None or setting.value != "on":
                return

        # edit their nickname
        if rolestate.nick is not None:
            await member.nickname.set(rolestate.nick)

        roles = self._unmap_rolestate(member.guild, rolestate.roles)
        await member.roles.add(*roles)

    @command()
    async def rolestate(self, ctx: Context):
        """
        Views the current rolestate setting for this guild.
        """

    @rolestate.subcommand()
    async def view(self, ctx: Context, target: int = None):
        """
        Views the rolestate for a user.
        """
        if target is None:
            target = ctx.author.id

        member = ctx.guild.members.get(target)
        if member is None:
            try:
                user = await ctx.bot.get_user(target)
            except NotFound:
                return await ctx.channel.messages.send(":x: This user does not exist.")
        else:
            user = member.user

        sess: Session = ctx.bot.db.get_session()
        async with sess:
            rolestate: tbl_rolestate = await sess.select(tbl_rolestate) \
                .where(tbl_rolestate.guild_id.eq(ctx.guild.id)) \
                .where(tbl_rolestate.user_id.eq(target)).first()

        em = Embed(title="Rolestate Viewer")
        if rolestate is None:
            # ensure we have a member to view
            member = ctx.guild.members.get(target)
            if member is None:
                em.description = "This member has no rolestate, and is not in this server."
                em.colour = 0xff0000
                return await ctx.channel.messages.send(embed=em)

            rolestate = await self.add_rolestate(member)

        roles: List[Role] = self._unmap_rolestate(ctx.guild, rolestate.roles)
        mentions: List[str] = map(operator.attrgetter('mention'),
                                  self._unmap_rolestate(ctx.guild, rolestate.roles))

        em.description = "This shows the most recent rolestate for a user ID."
        em.add_field(name="Username", value=user.username)
        em.add_field(name="Nickname", value=rolestate.nick)
        em.add_field(name="Roles", value=', '.join(mentions))
        em.set_footer(text=f"Rolestate for guild {ctx.guild.id}")
        em.set_thumbnail(url=user.static_avatar_url)
        colour = sorted(roles)[-1].colour
        em.colour = colour

        await ctx.channel.messages.send(embed=em)
