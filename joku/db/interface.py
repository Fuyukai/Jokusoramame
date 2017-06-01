import logging
import random
from contextlib import contextmanager
import datetime
import time
import typing

import discord
from asyncio_extras import threadpool
from sqlalchemy import Column, func
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import sessionmaker, Session

from joku.db.tables import User, RoleState, Guild, UserColour, EventSetting, Tag, Reminder, UserStock, Stock, \
    TagAlias

logger = logging.getLogger("Jokusoramame.DB")


# logging.getLogger("sqlalchemy").setLevel(logging.INFO)


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
        if dsn is None:
            raise ValueError("No DSN provided to connect to. Did you supply one in your config file?")

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
    async def get_or_create_guild(self, guild: discord.Guild) -> Guild:
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

    async def get_multiple_guilds(self, *guilds: typing.List[discord.Guild]) -> typing.Sequence[Guild]:
        """
        Gets multiple guilds.
        """
        async with threadpool():
            with self.get_session() as sess:
                g = sess.query(Guild).filter(Guild.id.in_([g.id for g in guilds])).all()

        return list(g)

    async def update_bulletin_message(self, guild: discord.Guild, channel: discord.TextChannel,
                                      message_id: int):
        """
        Modifies the bulletin message ID for a guild.
        """
        guild = await self.get_or_create_guild(guild)

        async with threadpool():
            with self.get_session() as sess:
                if channel is None:
                    guild.bulletin_channel = None
                else:
                    guild.bulletin_channel = channel.id
                guild.bulletin_message = message_id
                sess.add(guild)

        return guild

    # endregion

    # region User

    async def get_or_create_user(self, member: discord.Member = None, id: int = None) -> User:
        """
        Gets or creates a user object.
        """
        if member is not None:
            id = member.id

        async with threadpool():
            with self.get_session() as session:
                obb = session.query(User).filter(User.id == id).first()

                if obb is None:
                    obb = User(id=id)

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
        user = await self.get_or_create_user(member)
        async with threadpool():
            with self.get_session() as session:
                if xp_to_add is None:
                    xp_to_add = random.randint(0, 4)

                if user.xp is None:
                    user.xp = 0

                user.xp += xp_to_add
                user.last_modified = datetime.datetime.now()

                session.add(user)

        return user

    async def set_user_level(self, member: discord.Member, level: int) -> User:
        """
        Sets a user's level.
        """
        user = await self.get_or_create_user(member)
        async with threadpool():
            with self.get_session() as session:
                user.level = level
                user.last_modified = datetime.datetime.now()

                session.add(user)

        return user

    # endregion

    # region Settings

    async def get_setting(self, guild: discord.Guild, setting_name: str,
                          default: typing.Any = None) -> typing.Any:
        """
        Gets a setting.
        """
        async with threadpool():
            with self.get_session() as session:
                setting = session.query(Guild) \
                    .filter((Guild.id == guild.id) & (Guild.settings.has_key(setting_name))) \
                    .first()

                if setting:
                    return setting.settings[setting_name]
                else:
                    return default

    async def set_setting(self, guild: discord.Guild, setting_name: str, value: str) -> Guild:
        """
        Sets a setting Value.
        """
        async with threadpool():
            with self.get_session() as session:
                setting = session.query(Guild) \
                    .filter(Guild.id == guild.id) \
                    .one()

                setting.settings[setting_name] = value
                session.add(setting)
                session.commit()

        return setting

    # endregion

    # region Currency
    async def update_user_currency(self, member: discord.Member, currency_to_add: int) -> User:
        """
        Updates the user's current currency.
        """
        user = await self.get_or_create_user(member)
        async with threadpool():
            with self.get_session() as session:
                if user.money is not None:
                    user.money += currency_to_add
                else:
                    user.money = currency_to_add

                user.last_modified = datetime.datetime.now()

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
        user = await self.get_or_create_user(member)

        async with threadpool():
            with self.get_session() as session:
                assert isinstance(session, Session)

                current_rolestate = session.query(RoleState) \
                    .filter((RoleState.user_id == member.id) & (RoleState.guild_id == member.guild.id)) \
                    .first()

                if current_rolestate is None:
                    current_rolestate = RoleState(user_id=member.id)
                    current_rolestate.guild = guild

                # Add role IDs directly as an array.
                current_rolestate.nick = member.nick
                current_rolestate.roles = [r.id for r in member.roles if not r == member.guild.default_role]
                session.merge(user)
                session.add(current_rolestate)

        return current_rolestate

    async def get_rolestate_for_id(self, guild_id: int, member_id: int) -> typing.Union[RoleState, None]:
        """
        Gets the rolestate for a user by ID.
        """
        async with threadpool():
            with self.get_session() as session:
                assert isinstance(session, Session)

                rolestate = session.query(RoleState) \
                    .filter((RoleState.user_id == member_id) & (RoleState.guild_id == guild_id)) \
                    .first()

        return rolestate

    def get_rolestate_for_member(self, member: discord.Member) -> typing.Awaitable[typing.Union[RoleState, None]]:
        """
        Gets the rolestate for a member.
        """
        return self.get_rolestate_for_id(member.guild.id, member.id)

    # endregion

    # region Roleme
    async def get_roleme_roles(self, guild: discord.Guild) -> typing.List[discord.Role]:
        """
        Gets a list of roles that can be given to users by themselves.
        """
        g = await self.get_or_create_guild(guild)

        # load the role objects
        roles = [discord.utils.get(guild.roles, id=r_id) for r_id in g.roleme_roles]
        roles = [_ for _ in roles if _ is not None]

        return roles

    async def add_roleme_role(self, role: discord.Role) -> Guild:
        """
        Adds a role to the list of roleme roles.
        """
        g = await self.get_or_create_guild(role.guild)

        async with threadpool():
            with self.get_session() as session:
                if role.id not in g.roleme_roles:
                    # sqlalchemy won't track our append (w/o some arcane magic)
                    # so we copy the list
                    # then replace it
                    roles = g.roleme_roles.copy()
                    roles.append(role.id)
                    g.roleme_roles = roles

                session.add(g)

        return g

    async def remove_roleme_role(self, role: discord.Role) -> Guild:
        """
        Removes a role from the list of roleme roles.
        """
        g = await self.get_or_create_guild(role.guild)

        async with threadpool():
            with self.get_session() as session:
                if role.id not in g.roleme_roles:
                    # no-op
                    return g

                # copy it because sqlalchemy is f i c k l e
                roles = g.roleme_roles.copy()  # type: list
                roles.remove(role.id)
                g.roleme_roles = roles

                session.add(g)

        return g

    # endregion

    # region Colourme
    async def get_colourme_roles(self, guild: discord.Guild) -> typing.List[discord.Role]:
        """
        Gets all the colourme roles set on the server.
        """

        g = await self.get_or_create_guild(guild)

        # load the role objects
        roles = [discord.utils.get(guild.roles, id=r_id) for r_id in g.colourme_roles]
        roles = [_ for _ in roles if _ is not None]

        return roles

    async def add_colourme_role(self, role: discord.Role) -> Guild:
        """
        Adds a colourme to the list of colourme roles.
        """
        g = await self.get_or_create_guild(role.guild)

        async with threadpool():
            with self.get_session() as session:
                if role.id not in g.colourme_roles:
                    # sqlalchemy won't track our append (w/o some arcane magic)
                    # so we copy the list
                    # then replace it
                    roles = g.colourme_roles.copy()
                    roles.append(role.id)
                    g.colourme_roles = roles

                session.add(g)

        return g

    async def remove_colourme_role(self, role: discord.Role) -> Guild:
        """
        Removes a colour from the list of colourme roles.
        """
        g = await self.get_or_create_guild(role.guild)

        async with threadpool():
            with self.get_session() as session:
                if role.id not in g.colourme_roles:
                    # no-op
                    return g

                # copy it because sqlalchemy is f i c k l e
                roles = g.colourme_roles.copy()  # type: list
                roles.remove(role.id)
                g.colourme_roles = roles

                session.add(g)

        return g

    async def get_colourme_role(self, member: discord.Member) -> typing.Union[discord.Role, None]:
        """
        Gets the colourme role for a member.
        """
        async with threadpool():
            with self.get_session() as sess:
                uc = sess.query(UserColour) \
                    .filter((UserColour.user_id == member.id) & (UserColour.guild_id == member.guild.id)) \
                    .first()  # type: UserColour

                if uc is None:
                    return None

                role = discord.utils.get(member.guild.roles, id=uc.role_id)
                return role

    async def set_colourme_role(self, member: discord.Member, role: discord.Role) -> UserColour:
        """
        Sets the colourme role for a member.
        """
        guild = await self.get_or_create_guild(member.guild)
        user = await self.get_or_create_user(member)

        async with threadpool():
            with self.get_session() as sess:
                uc = sess.query(UserColour) \
                    .filter((UserColour.user_id == member.id) & (UserColour.guild_id == member.guild.id)) \
                    .first()  # type: UserColour

                if uc is None:
                    uc = UserColour()

                # update these, to be sure
                uc.role_id = role.id
                uc.guild = guild
                uc.user = user

                sess.add(uc)

        return uc

    # endregion

    # region Events
    async def get_enabled_events(self, guild: discord.Guild) -> typing.Sequence[str]:
        """
        Gets the enabled events for this guild.
        """
        guild = await self.get_or_create_guild(guild)

        async with threadpool():
            with self.get_session() as sess:
                # bind the guild to our session so we can access the event settings property
                sess.add(guild)

                event_names = [e.event for e in guild.event_settings if e.enabled is True]

                # now remove it from the session, no need to commit
                sess.expunge(guild)

        return event_names

    async def get_event_setting(self, guild: discord.Guild, event: str) -> typing.Union[EventSetting, None]:
        """
        Gets the EventSetting for the specified guild.
        """
        async with threadpool():
            with self.get_session() as sess:
                uc = sess.query(EventSetting) \
                    .filter((EventSetting.guild_id == guild.id) & (EventSetting.event == event)) \
                    .first()

                return uc

    async def update_event_setting(self, guild: discord.Guild, event: str, *,
                                   enabled: bool = None, message: str = None,
                                   channel: discord.TextChannel = None) -> EventSetting:
        """
        Updates an event setting.
        """
        original = await self.get_event_setting(guild, event)
        guild = await self.get_or_create_guild(guild)

        async with threadpool():
            with self.get_session() as sess:
                if original is None:
                    original = EventSetting(event=event)

                # add now, to prevent sqlalchemy being mean
                sess.add(original)

                # update backrefs
                original.guild = guild

                if enabled is not None:
                    original.enabled = enabled

                if message is not None:
                    original.message = message

                if channel is not None:
                    original.channel_id = channel.id

        return original

    # endregion

    # region Tags
    async def get_tag(self, guild: discord.Guild, name: str,
                      return_alias: bool = False) -> typing.Union[Tag, typing.Tuple[Tag, TagAlias]]:
        """
        Gets a tag from the database.
        """
        async with threadpool():
            with self.get_session() as sess:
                tag = sess.query(Tag) \
                    .filter((Tag.name == name) & (Tag.guild_id == guild.id)) \
                    .first()

                alias = None

                if tag is None:
                    alias = sess.query(TagAlias) \
                        .filter((TagAlias.alias_name == name) & (TagAlias.guild_id == guild.id)) \
                        .first()
                    if alias is not None:
                        tag = alias.tag
        if return_alias:
            return tag, alias
        else:
            return tag

    async def get_all_tags_for_guild(self, guild: discord.Guild) -> typing.Sequence[Tag]:
        """
        Gets all tags for this guild.
        """
        await self.get_or_create_guild(guild)

        async with threadpool():
            with self.get_session() as sess:
                return list(sess.query(Tag).filter(Tag.guild_id == guild.id).all())

    async def create_tag_alias(self, guild: discord.Guild, to_alias: Tag, alias_name: str,
                               owner: discord.Member) -> TagAlias:
        """
        Creates a tag alias.
        """
        await self.get_or_create_guild(guild)
        await self.get_or_create_user(owner)

        async with threadpool():
            with self.get_session() as sess:
                alias = TagAlias()
                alias.tag_id = to_alias.id
                alias.guild_id = guild.id
                alias.user_id = owner.id
                alias.alias_name = alias_name

                sess.add(alias)

        return alias

    async def remove_tag_alias(self, guild: discord.Guild, alias: TagAlias):
        """
        Removes a tag alias.
        """
        await self.get_or_create_guild(guild)
        async with threadpool():
            with self.get_session() as sess:
                sess.delete(alias)

        return alias

    async def save_tag(self, guild: discord.Guild, name: str, content: str, *,
                       owner: discord.Member = None, lua: bool = False) -> Tag:
        """
        Saves a tag to the database.
        """
        guild = await self.get_or_create_guild(guild)
        tag = await self.get_tag(guild, name)

        async with threadpool():
            with self.get_session() as sess:
                # add it first otherwise sqlalchemy cries
                if tag is None:
                    tag = Tag()
                sess.add(tag)

                # update tag
                tag.name = name
                tag.content = content
                tag.last_modified = datetime.datetime.now()
                if owner is not None:
                    tag.user_id = owner.id

                tag.guild_id = guild.id
                tag.lua = lua

        return tag

    async def delete_tag(self, guild: discord.Guild, name: str) -> typing.Union[Tag, None]:
        """
        Deletes a tag from the database.
        """
        tag = await self.get_tag(guild, name)

        if not tag:
            return

        async with threadpool():
            with self.get_session() as sess:
                sess.delete(tag)

                # find aliases that refer to this tag
                aliases = sess.query(TagAlias).filter(TagAlias.tag_id == tag.id).all()
                for alias in aliases:
                    sess.delete(alias)

        return tag

    # endregion

    # region Reminders
    async def scan_reminders(self, within: int = 300) -> typing.List[Reminder]:
        """
        Scans reminders, and checks which reminders are due to run within the next <within> seconds.
        """
        async with threadpool():
            with self.get_session() as sess:
                assert isinstance(sess, Session)

                dt = datetime.datetime.utcfromtimestamp(time.time() + within)

                # query all enabled reminders that are less than the remaining time
                reminders = sess.query(Reminder) \
                    .filter((Reminder.enabled == True) & (Reminder.reminding_at < dt)) \
                    .all()

                return list(reminders)

    async def create_reminder(self, channel: discord.TextChannel, member: discord.Member,
                              content: str, remind_at: datetime.datetime):
        """
        Creates a reminder for the specified member in the channel.
        """
        user = await self.get_or_create_user(member)

        async with threadpool():
            with self.get_session() as sess:
                # sqlalchemy woes
                sess.add(user)

                reminder = Reminder()
                reminder.channel_id = channel.id
                reminder.user = user
                reminder.text = content
                reminder.reminding_at = remind_at
                reminder.enabled = True
                sess.add(reminder)

        return reminder

    async def get_reminders_for(self, member: discord.Member) -> typing.Sequence[Reminder]:
        """
        Gets a list of reminders for a member.
        """
        async with threadpool():
            with self.get_session() as sess:
                reminders = sess.query(Reminder) \
                    .filter((Reminder.enabled == True) & (Reminder.user_id == member.id)) \
                    .first()

                return list(reminders)

    async def get_reminder(self, id: int) -> Reminder:
        """
        Gets a reminder by ID.
        """
        async with threadpool():
            with self.get_session() as sess:
                return sess.query(Reminder).filter(Reminder.id == id).first()

    async def cancel_reminder(self, id: int) -> Reminder:
        """
        Cancels a reminder by marking it as non active.
        """
        reminder = await self.get_reminder(id)
        async with threadpool():
            with self.get_session() as sess:
                sess.add(reminder)
                reminder.enabled = False

        return reminder

    # endregion

    # region Stocks
    async def get_user_stocks(self, user: discord.Member, *,
                              guild: discord.Guild = None) -> typing.Sequence[UserStock]:
        """
        Gets the stocks that a user owns.
        
        If guild is provided, this will only fetch stocks from that guild.
        """
        # always create if needed
        user = await self.get_or_create_user(user)
        if guild:
            g_obb = await self.get_or_create_guild(guild)
        else:
            g_obb = None

        async with threadpool():
            with self.get_session() as sess:
                assert isinstance(sess, Session)
                # if guild was provided, we want to do a joined query on `stock`
                if guild is not None:
                    query = sess.query(UserStock) \
                        .join(UserStock.stock) \
                        .filter((UserStock.user_id == user.id) & (Stock.guild_id == guild.id))
                else:
                    query = sess.query(UserStock) \
                        .filter(UserStock.user_id == user.id)

                results = list(query.all())
                return results

    async def get_user_stock(self, user: discord.Member, channel: discord.TextChannel) -> UserStock:
        """
        Gets a UserStock for the specified user and channel.
        """
        user = await self.get_or_create_user(user)

        async with threadpool():
            with self.get_session() as sess:
                assert isinstance(sess, Session)

                query = sess.query(UserStock) \
                    .join(Stock) \
                    .filter((UserStock.user_id == user.id) & (Stock.channel_id == channel.id)) \
                    .first()

        return query

    async def get_stocks_for(self, guild: discord.Guild) -> typing.Sequence[Stock]:
        """
        Gets the stocks for the specified guild.
        """
        g_obb = await self.get_or_create_guild(guild)

        async with threadpool():
            with self.get_session() as sess:
                assert isinstance(sess, Session)
                results = sess.query(Stock).filter(Stock.guild_id == guild.id).all()

        return list(results)

    async def get_stock(self, channel: discord.TextChannel) -> Stock:
        """
        Gets a stock for the specified channel.
        """
        g_obb = await self.get_or_create_guild(channel.guild)

        async with threadpool():
            with self.get_session() as sess:
                assert isinstance(sess, Session)

                stock = sess.query(Stock).filter(Stock.channel_id == channel.id).first()

        return stock

    async def get_remaining_stocks(self, channel: discord.TextChannel) -> int:
        """
        Gets the remaining amount of stocks for the stock associated w/ this channel. 
        """
        g_obb = await self.get_or_create_guild(channel.guild)

        async with threadpool():
            with self.get_session() as sess:
                assert isinstance(sess, Session)
                # use the `func.sum` function
                stock = sess.query(Stock).filter(Stock.channel_id == channel.id).first()
                if stock is None:
                    return 0

                # evil query ahead
                total = sess.query(func.sum(UserStock.amount)) \
                    .filter(UserStock.stock_id == stock.channel_id) \
                    .scalar()

                if total is None:
                    return stock.amount

        return stock.amount - total

    async def bulk_get_remaining_stocks(self, *stocks: typing.Iterable[Stock]):
        """
        Bulk gets the remaining stocks for a series of stocks.
        
        This is faster than calling the amount of stocks repeatedly.
        """
        async with threadpool():
            with self.get_session() as sess:
                sql = ("SELECT user__stock.stock_id, sum(user__stock.amount) "
                       "FROM user__stock "
                       "WHERE user__stock.stock_id IN :values "
                       "GROUP BY user__stock.stock_id")
                cursor = sess.execute(sql, {"values": tuple(stock.channel_id for stock in stocks)})
                rows = cursor.fetchall()

        return {
            stock_id: sum for (stock_id, sum) in rows
        }

    async def change_stock(self, channel: discord.TextChannel, *,
                           amount: int = None, price: int = None) -> Stock:
        """
        Changes the stock for the specified channel.
        
        If the stock already exists, the properties are updated.
        
        :param amount: The amount of stocks to create.
        :param price: The price of this stock.
        """
        guild = await self.get_or_create_guild(channel.guild)

        async with threadpool():
            with self.get_session() as sess:
                assert isinstance(sess, Session)
                stock = Stock()
                # update the appropriate fields
                stock.channel_id = channel.id
                stock.guild = guild

                if amount is not None:
                    stock.amount = amount
                if price is not None:
                    stock.price = price

                sess.merge(stock)

        return stock

    async def change_user_stock_amount(self, user: discord.Member, channel: discord.TextChannel, *,
                                       amount: int, crashed: bool = None, update_price: bool = True):
        """
        Changes the amount of stock a user owns.
        
        This will update their currency as appropriate, but will NOT do any bounds checking.
        """
        user = await self.get_or_create_user(user)
        ustock = await self.get_user_stock(user, channel)
        if not ustock:
            ustock = UserStock()
            ustock.user_id = user.id  # will always exist
            ustock.stock = await self.get_stock(channel)
            # udpate manually
            ustock.stock_id = ustock.stock.channel_id

        async with threadpool():
            with self.get_session() as sess:
                assert isinstance(sess, Session)
                # allow the session to now load the stock object
                # no autoflush required for sqlalchemy to not die when querying
                with sess.no_autoflush:
                    if ustock.amount is not None:
                        ustock.amount += amount
                    else:
                        ustock.amount = amount

                    if update_price:
                        user.money += int(-amount * ustock.stock.price)

                    if crashed is not None:
                        ustock.crashed = crashed

                    sess.merge(ustock)
                    sess.merge(user)

        return ustock
