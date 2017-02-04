import logging
import random
from contextlib import contextmanager

import discord
import typing
from asyncio_extras import threadpool
from sqlalchemy import Column
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import sessionmaker, Session

from joku.db.tables import User, Setting, RoleState, Guild

logger = logging.getLogger("Jokusoramame.DB")
logging.getLogger("sqlalchemy").setLevel(logging.INFO)


class DatabaseInterface(object):
    """
    A wrapper for the PostgreSQL database.
    """

    def __init__(self, bot):
        self.bot = bot

        self.engine = None  # type: Engine
        self._sessionmaker = None  # type: sessionmaker

    async def connect(self, dsn: str):
        """
        Connects the bot to the database.
        """
        logger.info("Connecting to {}...".format(dsn))
        async with threadpool():
            self.engine = create_engine(dsn)
            self._sessionmaker = sessionmaker(bind=self.engine, expire_on_commit=False)

    @contextmanager
    def get_session(self) -> Session:
        session = self._sessionmaker()  # type: Session

        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()

    # region Guild
    async def get_or_create_guild(self, guild: discord.Guild):
        """
        Creates or gets a guild object from the database.
        """
        async with threadpool():
            with self.get_session() as sess:
                g = sess.query(Guild).filter(Guild.id == guild.id).first()

                if g is None:
                    g = Guild(id=guild.id)
                    sess.add(g)

        return g

    # region User

    async def get_or_create_user(self, member: discord.Member, *, detatch: bool = False) -> User:
        """
        Gets or creates a user object.
        """
        async with threadpool():
            with self.get_session() as session:
                obb = session.query(User).filter(User.id == member.id).first()

                if obb is None:
                    obb = User(id=member.id)

        return obb

    async def get_multiple_users(self, *members: discord.Member, order_by: Column = None,
                                 detatch: bool = False):
        """
        Gets multiple user objects.

        This will **not** create them if they don't exist.
        """
        ids = [u.id for u in members]

        async with threadpool():
            with self.get_session() as session:
                _q = session.query(User).filter(User.id.in_(ids))
                if order_by is not None:
                    _q = _q.order_by(order_by)

                obbs = list(_q.all())

                # Detach all from their sessions.
                if detatch:
                    [session.expunge(obb) for obb in obbs]

            return obbs

    async def update_user_xp(self, member: discord.Member, xp_to_add: int = None) -> User:
        """
        Updates the XP of a user.
        """
        user = await self.get_or_create_user(member, detatch=True)
        async with threadpool():
            with self.get_session() as session:
                if xp_to_add is None:
                    xp_to_add = random.randint(0, 4)

                if user.xp is None:
                    user.xp = 0

                user.xp += xp_to_add

                session.add(user)

        return user

    async def set_user_level(self, member: discord.Member, level: int) -> User:
        """
        Sets a user's level.
        """
        user = await self.get_or_create_user(member, detatch=True)
        async with threadpool():
            with self.get_session() as session:
                user.level = level
                session.add(user)

        return user

    # endregion

    # region Settings

    async def get_setting(self, guild: discord.Guild, setting_name: str, default: typing.Any = None) -> dict:
        """
        Gets a setting.
        """
        async with threadpool():
            with self.get_session() as session:
                setting = session.query(Setting) \
                    .filter((Setting.guild_id == guild.id) | (Setting.name == setting_name)) \
                    .first()

                if setting:
                    return setting.value
                else:
                    return default

    async def set_setting(self, guild: discord.Guild, setting_name: str, value: dict=None, **kwargs) -> Setting:
        """
        Sets a setting value.
        """
        g = await self.get_or_create_guild(guild)

        async with threadpool():
            with self.get_session() as session:
                setting = session.query(Setting) \
                    .filter(Setting.guild_id == guild.id and Setting.name == setting_name) \
                    .first()

                if setting is None:
                    setting = Setting(name=setting_name)
                    setting.guild = g

                if value is None:
                    value = {}

                value = {**value, **kwargs}

                setting.value = value
                session.add(setting)

        return setting

    # endregion

    # region Currency
    async def update_user_currency(self, member: discord.Member, currency_to_add: int) -> User:
        """
        Updates the user's current currency.
        """
        user = await self.get_or_create_user(member, detatch=True)
        async with threadpool():
            with self.get_session() as session:
                user.money += currency_to_add

                session.add(user)

        return user

    async def get_user_currency(self, member: discord.Member):
        """
        Gets the currency for a specified member.
        """
        user = await self.get_or_create_user(member)

        return user.money

    # endregion

    # region Rolestate

    async def save_rolestate(self, member: discord.Member) -> RoleState:
        """
        Saves the rolestate for a member.
        """
        guild = await self.get_or_create_guild(member.guild)

        async with threadpool():
            with self.get_session() as session:
                assert isinstance(session, Session)

                current_rolestate = session.query(RoleState)\
                    .filter((RoleState.user_id == member.id) | (RoleState.guild_id == member.guild.id))\
                    .first()

                if current_rolestate is None:
                    current_rolestate = RoleState(user_id=member.id)
                    current_rolestate.guild = guild

                # Add role IDs directly as an array.
                current_rolestate.nick = member.nick
                current_rolestate.roles = [r.id for r in member.roles]
                session.add(current_rolestate)

        return current_rolestate

    async def get_rolestate_for_id(self, guild_id: int, member_id: int) -> typing.Union[RoleState, None]:
        """
        Gets the rolestate for a user by ID.
        """
        async with threadpool():
            with self.get_session() as session:
                assert isinstance(session, Session)

                rolestate = session.query(RoleState)\
                    .filter((RoleState.user_id == member_id) | (RoleState.guild_id == guild_id))\
                    .first()

        return rolestate

    def get_rolestate_for_member(self, member: discord.Member) -> typing.Awaitable[typing.Union[RoleState, None]]:
        """
        Gets the rolestate for a member.
        """
        return self.get_rolestate_for_id(member.guild.id, member.id)
