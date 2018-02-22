"""
Roleme stuff.
"""

from asyncqlio import Session
from asyncqlio.orm.query import ResultGenerator
from curious import Role
from curious.commands import Context, Plugin, command, condition

from jokusoramame.db.tables import RolemeRole


class Roleme(Plugin):
    """
    Commands for the roleme portion of the bot.
    """

    @command()
    async def roleme(self, ctx: Context, *, role: Role = None):
        """
        Adds a role to your list of roles.
        """
        sess: Session = ctx.bot.db.get_session()
        async with sess:
            rolemes: ResultGenerator = await sess.select(RolemeRole) \
                .where(RolemeRole.guild_id.eq(ctx.guild.id)) \
                .all()

            role_ids = [rolemerole.id async for rolemerole in rolemes if rolemerole.self_assignable]

        # behaviour a, assign a role
        if role is not None:
            if role.id not in role_ids:
                return await ctx.channel.messages.send(":x: This role is not self-assignable.")

            await ctx.author.roles.add(role)
            return await ctx.channel.messages.send(":heavy_check_mark: Assigned you this role.")
        else:
            if not role_ids:
                return await ctx.channel.messages.send(":pencil: There are no roles you can assign "
                                                       "yourself in this server currently.")

            fmts = []
            for role_id in role_ids:
                role = ctx.guild.roles.get(role_id)
                if not role:
                    continue

                fmts.append(" - {}".format(role.name))
            list = '\n'.join(fmts)
            return await ctx.channel.messages.send(f":pencil: **Roles you can give yourself:**"
                                                   f"\n\n{list}")

    @roleme.subcommand()
    @condition(lambda ctx: ctx.author.guild_permissions.manage_roles)
    async def add(self, ctx: Context, *, role: Role = None):
        """
        Adds a role as a roleme role.
        """
        sess: Session = ctx.bot.db.get_session()
        async with sess:
            roleme = RolemeRole()
            roleme.guild_id = ctx.guild.id
            roleme.id = role.id
            roleme.self_assignable = True
            await sess.insert.rows(roleme) \
                .on_conflict(RolemeRole.id) \
                .update(RolemeRole.self_assignable) \
                .run()

        await ctx.channel.messages.send(f":heavy_check_mark: Added {role.name} as a roleme role.")

    @roleme.subcommand()
    @condition(lambda ctx: ctx.author.guild_permissions.manage_roles)
    async def remove(self, ctx: Context, *, role: Role = None):
        """
        Removes a role as a roleme role.
        """
        sess: Session = ctx.bot.db.get_session()
        async with sess:
            await sess.update.where(RolemeRole.id.eq(role.id))\
                .set(RolemeRole.self_assignable, False).run()

        await ctx.channel.messages.send(f":heavy_check_mark: Removed {role.name} as a roleme role.")

    @roleme.subcommand()
    async def unroleme(self, ctx: Context, *, role: Role):
        """
        Removes a role from you.
        """
        sess: Session = ctx.bot.db.get_session()
        async with sess:
            rolemes: ResultGenerator = await sess.select(RolemeRole) \
                .where(RolemeRole.guild_id.eq(ctx.guild.id)) \
                .all()

            role_ids = [rolemerole.id async for rolemerole in rolemes if rolemerole.self_assignable]

        if role.id not in role_ids:
            return await ctx.channel.messages.send(":x: This role is not self-assignable.")

        await ctx.author.roles.remove(role)
        await ctx.channel.messages.send(":heavy_check_mark: Removed you from this role.")