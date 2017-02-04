import logging
import random

import discord
import typing
from asyncio_extras import threadpool
from sqlalchemy import Column
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import sessionmaker, Session

from joku.db.tables import User, Setting

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

        self.session = None  # type: Session

    async def connect(self, dsn: str):
        """
        Connects the bot to the database.
        """
        logger.info("Connecting to {}...".format(dsn))
        async with threadpool():
            if self.engine is not None:
                # Close the session.
                self.session.close()

            self.engine = create_engine(dsn)
            self._sessionmaker = sessionmaker(bind=self.engine)

            # Create our session object.
            self.session = self._sessionmaker()

    async def get_or_create_user(self, member: discord.Member) -> User:
        """
        Gets or creates a user object.
        """
        async with threadpool():
            obb = self.session.query(User).filter(User.id == member.id).first()

            if obb is None:
                obb = User(id=member.id)
                self.session.add(obb)
                self.session.commit()

        return obb

    async def get_multiple_users(self, *members: discord.Member, order_by: Column=None):
        """
        Gets multiple user objects.

        This will **not** create them if they don't exist.
        """
        ids = [u.id for u in members]

        async with threadpool():
            _q = self.session.query(User).filter(User.id.in_(ids))
            if order_by is not None:
                _q = _q.order_by(order_by)

            obbs = list(_q.all())

            return obbs

    async def update_user_xp(self, member: discord.Member, xp_to_add: int = None) -> User:
        """
        Updates the XP of a user.
        """
        user = await self.get_or_create_user(member)
        async with threadpool():
            if xp_to_add is None:
                xp_to_add = random.randint(0, 4)

            user.xp += xp_to_add

            self.session.add(user)
            self.session.commit()

        return user

    async def set_user_level(self, member: discord.Member, level: int) -> User:
        """
        Sets a user's level.
        """
        user = await self.get_or_create_user(member)
        async with threadpool():
            user.level = level
            self.session.add(user)
            self.session.commit()

        return user

    # region Settings

    async def get_setting(self, guild: discord.Guild, setting_name: str, default: typing.Any = None) -> dict:
        """
        Gets a setting.
        """
        async with threadpool():
            setting = self.session.query(Setting)\
                .filter(Setting.guild_id == guild.id and Setting.name == setting_name)\
                .first()

            if setting:
                return setting.value
            else:
                return default

    async def set_setting(self, guild: discord.Guild, setting_name: str, value: dict) -> Setting:
        """
        Sets a setting value.
        """
        async with threadpool():
            setting = self.session.query(Setting)\
                .filter(Setting.guild_id == guild.id and Setting.name == setting_name)\
                .first()

            if setting is not None:
                setting = Setting(name=setting_name, guild_id=guild.id)

            setting.value = value
            self.session.add(setting)
            self.session.commit()

        return setting

    # endregion

    # region Currency
    async def update_user_currency(self, member: discord.Member, currency_to_add: int) -> User:
        """
        Updates the user's current currency.
        """
        user = await self.get_or_create_user(member)
        async with threadpool():
            user.money += currency_to_add

            self.session.add(user)
            self.session.commit()

        return user

    async def get_user_currency(self, member: discord.Member):
        """
        Gets the currency for a specified member.
        """
        user = await self.get_or_create_user(member)

        return user.money

    # endregion
