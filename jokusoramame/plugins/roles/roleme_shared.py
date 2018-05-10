"""
Shared components between the RoleMe and ColourMe plugins.
"""
import enum
from asyncqlio import Session
from asyncqlio.orm.query import ResultGenerator
from curious import Guild, Member, Role
from typing import List

from jokusoramame.bot import Jokusoramame
from jokusoramame.db.tables import RolemeRole


class RolemeResult(enum.Enum):
    SUCCESS = 0
    ERR_NOT_ASSIGNABLE = 1


class RolemeShared(object):
    """
    Represents shared data between the RoleMe and ColourMe plugins.
    """
    def __init__(self, client: Jokusoramame):
        self.client = client

    async def get_all_roleme_roles(self, guild: Guild, *, colourme: bool = False) -> List[Role]:
        """
        Gets all the available RoleMe roles.

        :param guild: The :class:`.Guild` to look up roles from.
        :param colourme: If this search is for ColourMe roles.
        :return: A list of :class:`.Role` objects.
        """
        sess: Session = self.client.db.get_session()
        async with sess:
            rolemes: ResultGenerator = await sess.select(RolemeRole) \
                .where(RolemeRole.guild_id.eq(guild.id))\
                .where(RolemeRole.colourme.eq(colourme))\
                .all()

            rolemei: List[RolemeRole] = await rolemes.flatten()
            roles = [guild.roles.get(roleme.id) for roleme in rolemei]
            # cleanup scope, not for performance
            del rolemes, rolemei

        return roles

    async def apply_roleme_role(self, role: Role, target: Member) -> RolemeResult:
        """
        Adds a roleme role to the specified user.
        """
        sess: Session = self.client.db.get_session()
        async with sess:
            roleme: RolemeRole = await sess.select(RolemeRole) \
                .where(RolemeRole.id.eq(role.id))\
                .first()

            if not roleme.self_assignable:
                return RolemeResult.ERR_NOT_ASSIGNABLE

        await target.roles.add(role)
        return RolemeResult.SUCCESS

    async def unapply_roleme_role(self, role: Role, target: Member) -> RolemeResult:
        """
        Removes a roleme role from the specified user.
        """
        sess: Session = self.client.db.get_session()
        async with sess:
            roleme: RolemeRole = await sess.select(RolemeRole) \
                .where(RolemeRole.id.eq(role.id)) \
                .first()

            if not roleme.self_assignable:
                return RolemeResult.ERR_NOT_ASSIGNABLE

        await target.roles.remove(role)
        return RolemeResult.SUCCESS

    async def add_roleme_role(self, role: Role, *, is_colourme: bool = False):
        """
        Adds a role to the list of RoleMe roles.
        """
        sess: Session = self.client.db.get_session()
        async with sess:
            roleme = RolemeRole()
            roleme.guild_id = role.guild_id
            roleme.id = role.id
            roleme.self_assignable = True
            roleme.colourme = is_colourme
            await sess.insert.rows(roleme) \
                .on_conflict(RolemeRole.id) \
                .update(RolemeRole.self_assignable)\
                .update(RolemeRole.colourme) \
                .run()

    async def remove_roleme_role(self, role: Role):
        """
        Removes a role from the list of RoleMe roles.
        """
        sess: Session = self.client.db.get_session()

        async with sess:
            await sess.update.table(RolemeRole) \
                .where(RolemeRole.id == role) \
                .set(RolemeRole.self_assignable, False) \
                .run()
