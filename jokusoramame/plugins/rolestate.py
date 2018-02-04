from asyncqlio import Session
from curious import Member, EventContext, event
from curious.commands import Plugin

from jokusoramame.db.tables import Rolestate as tbl_rolestate
from jokusoramame.db.tables import GuildSetting as tbl_gsetting


class Rolestate(Plugin):
    """
    Plugin for rolestate.
    """
    @event("guild_member_remove")
    async def update_rolestate(self, ctx: EventContext, member: Member):
        """
        Updates the rolestate for a member.
        """
        rolestate = tbl_rolestate(user_id=member.id, guild_id=member.guild_id,
                                  nick=str(member.nickname) if member.nickname else None,
                                  roles=",".join(map(str, member.role_ids)))

        sess: Session = ctx.bot.db.get_session()
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

        roles = map(member.guild.roles.get, map(int, rolestate.roles.split(",")))
        await member.roles.add(*roles)
