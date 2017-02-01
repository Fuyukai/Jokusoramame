"""
A RethinkDB database interface.
"""
import datetime
import random
import typing

import discord
import logbook
import time

import rethinkdb as r
import pytz

from joku.utils import get_role
from rethinkdb.asyncio_net.net_asyncio import AsyncioCursor

r.set_loop_type("asyncio")


class RethinkAdapter(object):
    """
    An adapter to RethinkDB.
    """

    def __init__(self, bot):
        self.connection = None  # type: r.Connection

        self.bot = bot
        self.logger = bot.logger  # type: logbook.Logger

    # region Helpers

    async def _reql_safe(self, awaitable):
        """
        Runs a REQL operation, but ignoring r.RuntimeError.
        """
        try:
            res = await awaitable.run(self.connection)
        except (r.ReqlRuntimeError, r.ReqlOpFailedError) as e:
            if "already exists" in e.message:
                return
            self.logger.warn("Failed to run REQL operation: {}".format(e))
        else:
            self.logger.info("Ran {}.".format(awaitable))
            return res

    async def _setup(self):
        """
        Ugh.
        """
        if self.bot.shard_id != 0:
            # Only create on shard 0.
            return
        # Make the DB.
        await self._reql_safe(r.db_create("jokusoramame"))
        # Make the tables.
        await self._reql_safe(r.table_create("settings"))
        await self._reql_safe(r.table_create("users"))
        await self._reql_safe(r.table_create("tags"))
        await self._reql_safe(r.table_create("todos"))
        await self._reql_safe(r.table_create("reminders"))
        await self._reql_safe(r.table_create("rolestate"))
        await self._reql_safe(r.table_create("roleme_roles"))
        await self._reql_safe(r.table_create("roleme_colours"))

        # Create indexes.
        await self._reql_safe(r.table("settings").index_create("server_id"))
        await self._reql_safe(r.table("users").index_create("user_id"))
        await self._reql_safe(r.table("tags").index_create("server_id"))
        await self._reql_safe(r.table("todos").index_create("user_id"))
        await self._reql_safe(r.table("reminders").index_create("user_id"))
        await self._reql_safe(r.table("rolestate").index_create("server_id"))
        await self._reql_safe(r.table("roleme_roles").index_create("server_id"))
        await self._reql_safe(r.table("roleme_colours").index_create("server_id"))

    async def connect(self, **connection_settings):
        """
        Connects the adapter.
        """
        self.connection = await r.connect(**connection_settings)
        await self._setup()

    async def to_list(self, cursor) -> list:
        """
        Gets all items from an AsyncioCursor.
        """
        l = []
        while await cursor.fetch_next():
            l.append(await cursor.next())

        return l

    # endregion
    # region Generic Actions
    async def create_or_get_user(self, user: discord.User) -> dict:
        iterator = await r.table("users").get_all(str(user.id), index="user_id").run(self.connection)

        exists = await iterator.fetch_next()
        if not exists:
            # Create a new user.
            return {
                "user_id": str(user.id),
                "xp": 0,
                "rep": 0,
                "currency": 200,
                "level": 1,
                "inventory": [
                    {"id": 1, "count": 1}  # oppressed worker is ID 1
                ]
            }

        else:
            # Get the next item from the iterator.
            # Hopefully, this is the right one.
            d = await iterator.next()
            return d

    async def get_multiple_users(self, *users: typing.List[discord.User], order_by=None):
        """
        Gets multiple users.
        """
        ids = [str(u.id) for u in users]

        # Do a get_all using the ids as the items.
        _q = r.table("users").get_all(*ids, index="user_id")
        if order_by is None:
            iterator = await _q.run(self.connection)
            users = await self.to_list(iterator)
        else:
            iterator = await _q.order_by(order_by).run(self.connection)
            users = iterator

        return users

    # endregion
    # region Tags
    async def get_all_tags_for_server(self, guild: discord.Guild):
        """
        Returns all tags for a server
        """
        iterator = await r.table("tags") \
            .get_all(str(guild.id), index="server_id").run(self.connection)

        exists = iterator.fetch_next()
        if not exists:
            return None

        tags = []
        while await iterator.fetch_next():
            tags.append(await iterator.next())
        return tags

    async def get_tag(self, guild: discord.Guild, name: str) -> dict:
        """
        Gets a tag from the database.
        """
        iterator = await r.table("tags") \
            .get_all(str(guild.id), index="server_id") \
            .filter({"name": name}).run(self.connection)

        exists = await iterator.fetch_next()
        if not exists:
            return

        tag = await iterator.next()

        return tag

    async def save_tag(self, guild: discord.Guild, name: str, content: str, variables: dict,
                       *, owner: discord.User = None):
        """
        Saves a tag to the database.

        Will overwrite the tag if applicable.
        """
        if isinstance(owner, discord.User):
            owner_id = str(owner.id)
        else:
            owner_id = owner

        current_tag = await self.get_tag(guild, name)
        if current_tag is None:
            d = {
                "name": name,
                "content": content,
                "owner_id": owner_id if owner_id else None,
                "server_id": str(guild.id),
                "last_modified": datetime.datetime.now(tz=pytz.timezone("UTC")),
                "variables": variables
            }

        else:
            # Edit the current_tag dict with the new data.
            d = current_tag
            d["content"] = content
            d["last_modified"] = datetime.datetime.now(tz=pytz.timezone("UTC"))
            d["variables"] = variables

        d = await r.table("tags") \
            .insert(d, conflict="update") \
            .run(self.connection)

        return d

    async def delete_tag(self, guild: discord.Guild, name: str):
        """
        Deletes a tag.
        """
        d = await r.table("tags") \
            .get_all(str(guild.id), index="server_id") \
            .filter({"name": name}) \
            .delete() \
            .run(self.connection)

        return d

    # endregion
    # region XP
    async def get_level(self, user: discord.User):
        u = await self.create_or_get_user(user)
        return u["level"]

    async def update_user_xp(self, user: discord.User, xp=None) -> dict:
        """
        Updates the user's current experience.
        """
        user_dict = await self.create_or_get_user(user)

        # Add a random amount of exp.
        # lol rng
        if xp:
            added = xp
        else:
            added = random.uniform(0, 4)

        added = int(round(added, 0))

        user_dict["xp"] += added
        user_dict["last_modified"] = datetime.datetime.now(tz=pytz.timezone("UTC"))

        d = await r.table("users") \
            .insert(user_dict, conflict="update") \
            .run(self.connection)

        return user_dict

    async def get_user_xp(self, user: discord.User) -> int:
        """
        Gets the user's current experience.
        """
        user_dict = await self.create_or_get_user(user)

        return user_dict["xp"]

    # endregion
    # region Currency
    async def update_user_currency(self, user: discord.User, currency=None) -> dict:
        """
        Updates the user's current currency.
        """
        user_dict = await self.create_or_get_user(user)

        if currency:
            added = currency
        else:
            added = 50

        # Failsafe
        if 'currency' not in user_dict:
            user_dict['currency'] = 200

        user_dict["currency"] += added
        user_dict["last_modified"] = datetime.datetime.now(tz=pytz.timezone("UTC"))

        d = await r.table("users") \
            .insert(user_dict, conflict="update") \
            .run(self.connection)

        return d

    async def get_user_currency(self, user: discord.User) -> int:
        """
        Gets the user's current currency.
        """
        user_dict = await self.create_or_get_user(user)

        return user_dict.get("currency", 200)

    # endregion
    # region Settings
    async def set_setting(self, guild: discord.Guild, setting_name: str, **values: dict) -> dict:
        """
        Sets a setting.
        :param guild: The server to set the setting in.
        :param setting_name: The name to use.
        :param values: The values to insert into the settings.
        """
        # Try and find the ID.
        setting = await self.get_setting(guild, setting_name)
        if not setting:
            d = {"server_id": str(guild.id), "name": setting_name, **values}
        else:
            # Use the ID we have.
            d = {"server_id": str(guild.id), "name": setting_name, "id": setting["id"], **values}

        d = await r.table("settings") \
            .insert(d, conflict="update") \
            .run(self.connection)

        return d

    async def get_setting(self, guild: discord.Guild, setting_name: str, default=None) -> dict:
        """
        Gets a setting from RethinkDB.
        :param guild: The server to get the setting from.
        :param setting_name: The name to retrieve.
        :param default: The default value.
        """
        d = await r.table("settings") \
            .get_all(str(guild.id), index="server_id") \
            .filter({"name": setting_name}) \
            .run(self.connection)

        # Only fetch one.
        # There should only be one, anyway.
        fetched = await d.fetch_next()
        if not fetched:
            return default

        i = await d.next()
        return i

    async def get_event_message(self, guild: discord.Guild, event: str, default: str = "") \
            -> typing.Tuple[discord.TextChannel, str]:
        """
        Gets an event message, if the event exists.
        """
        enabled = await self.get_setting(guild, "events")
        if not enabled:
            return

        events = enabled.get("events", {})
        if not events.get(event):
            return

        channel = guild.get_channel(int(events[event]))
        if not channel:
            return

        message = await r.table("settings") \
            .get_all(str(guild.id), index="server_id") \
            .filter({"name": "event_msg", "event": event}) \
            .run(self.connection)

        l = await self.to_list(message)
        if not l:
            return channel, default

        message = l[0].get("msg", default)

        return channel, message

    # endregion
    # region Ignores
    async def is_channel_ignored(self, channel: discord.TextChannel, type_: str = "levelling"):
        """
        Checks if a channel has an ignore rule on it.
        """
        cursor = await r.table("settings") \
            .get_all(str(channel.guild.id), index="server_id") \
            .filter({"name": "ignore", "target": channel.id, "type": type_}) \
            .run(self.connection)

        items = await self.to_list(cursor=cursor)
        # Hacky thing
        # Turns a truthy value into True
        # and a falsey value ([], None) into False
        return not not items

    # endregion
    # region TODOs
    async def get_user_todos(self, user: discord.User) -> typing.List[dict]:
        """
        Gets a list of TODO entries for a user.
        """
        items = await r.table("todos") \
            .get_all(str(user.id), index="user_id") \
            .order_by("priority") \
            .run(self.connection)

        return items

    async def add_user_todo(self, user: discord.User, content: str, priority: int = None):
        """
        Adds a TODO for a user.
        """
        d = {
            "user_id": str(user.id),
            "content": content
        }

        if priority is None:
            priority = len(await self.get_user_todos(user)) + 1

        d["priority"] = priority

        i = await r.table("todos").insert(d, return_changes=True).run(self.connection)
        return i

    async def edit_user_todo(self, user: discord.User, index: int, new_content: str):
        """
        Edits a user's TODO.
        """
        i = await r.table("todos") \
            .get_all(str(user.id), index="user_id") \
            .filter({"priority": index}) \
            .update({"content": new_content}, return_changes=True) \
            .run(self.connection)

        return i

    async def delete_user_todo(self, user: discord.User, index: int):
        """
        Deletes a user's TODO.

        This will bump down all of the other indexes by one
        """
        # Delete the entry with the specified index.
        i1 = await r.table("todos") \
            .get_all(str(user.id), index="user_id") \
            .filter({"priority": index}) \
            .delete(return_changes=True) \
            .run(self.connection)

        # Now move all of the indexes down.
        i2 = await r.table("todos") \
            .get_all(str(user.id), index="user_id") \
            .filter(r.row["priority"] > index) \
            .update({"priority": r.row["priority"] - 1},
                    return_changes=True) \
            .run(self.connection)

        return [i1, i2]

    # endregion
    # region Rolestate
    async def save_rolestate(self, member: discord.Member):
        """
        Saves the rolestate for a specified member.
        """
        role_ids = [str(role.id) for role in member.roles if role is not member.guild.default_role
                    and role.position < member.guild.me.top_role.position]

        obb = {
            "server_id": str(member.guild.id),
            "user_id": str(member.id),
            "roles": role_ids,
            "user_nickname": member.nick,
            "saved_at": datetime.datetime.now(tz=pytz.timezone("UTC")),
        }

        # Get the existing ID to overwrite, if possible
        cursor = await r.table("rolestate") \
            .get_all(str(member.guild.id), index="server_id") \
            .filter({"user_id": str(member.id)}) \
            .limit(1) \
            .get_field("id") \
            .run(self.connection)

        l = await self.to_list(cursor)
        if l:
            obb["id"] = l[0]

        return await r.table("rolestate") \
            .insert(obb, return_changes=True, conflict="update") \
            .run(self.connection)

    async def get_rolestate_for_member(self, member: discord.Member) \
            -> typing.Tuple[typing.List[discord.Role], str]:
        """
        Gets the saved roles for a member.

        :param member: The member to get the roles of.
        :return: A list of roles that this member should have.
        """
        cursor = await r.table("rolestate") \
            .get_all(str(member.guild.id), index="server_id") \
            .filter({"user_id": str(member.id)}) \
            .limit(1) \
            .run(self.connection)

        try:
            obb = (await self.to_list(cursor))[0]
        except IndexError:
            return [], ""

        return [get_role(member.guild, int(role_id)) for role_id in obb["roles"]], obb["user_nickname"]

    # endregion
    # region Roleme
    async def add_roleme_role(self, guild: discord.Guild, role: discord.Role):
        """
        Adds a role that can be given to users.
        """
        guild_obb = await r.table("roleme_roles") \
            .get_all(str(guild.id), index="server_id") \
            .run(self.connection)  # type: AsyncioCursor

        try:
            guild_obb = await guild_obb.__anext__()
        except StopAsyncIteration:
            guild_obb = {
                "server_id": str(guild.id),
                "roles": []
            }

        if role.id not in guild_obb["roles"]:
            guild_obb["roles"].append(str(role.id))

        return await r.table("roleme_roles") \
            .insert(guild_obb, conflict="update", return_changes=True) \
            .run(self.connection)

    async def get_roleme_roles(self, guild: discord.Guild) -> typing.List[discord.Role]:
        """
        Gets a list of roles that can be given to users.
        """
        guild_obb = await r.table("roleme_roles") \
            .get_all(str(guild.id), index="server_id") \
            .run(self.connection)

        try:
            guild_obb = await guild_obb.__anext__()
        except StopAsyncIteration:
            return []

        return [get_role(guild, int(role_id)) for role_id in guild_obb["roles"]]

    async def remove_roleme_role(self, guild: discord.Guild, role: discord.Role):
        """
        Removes a role from the list of roles that can be given to users.
        """
        guild_obb = await r.table("roleme_roles") \
            .get_all(str(guild.id), index="server_id") \
            .run(self.connection)  # type: AsyncioCursor

        try:
            guild_obb = await guild_obb.__anext__()
        except StopAsyncIteration:
            return

        if str(role.id) in guild_obb["roles"]:
            guild_obb["roles"].remove(str(role.id))

        return await r.table("roleme_roles") \
            .insert(guild_obb, conflict="update", return_changes=True) \
            .run(self.connection)

    async def get_colourme_role(self, member: discord.Member) -> typing.Union[None, int]:
        """
        Gets the role that should be used for `colourme`.
        """
        role_id = await r.table("roleme_colours") \
            .get_all(str(member.guild.id), index="server_id") \
            .filter({"user_id": str(member.id)}) \
            .get_field("role_id") \
            .run(self.connection)

        try:
            return int(await role_id.__anext__())
        except StopAsyncIteration:
            return None

    async def set_colourme_role(self, member: discord.Member, role: discord.Role):
        """
        Sets the colourme role for a member.
        """
        previous = await r.table("roleme_colours") \
            .get_all(str(member.guild.id), index="server_id") \
            .filter({"user_id": member.id}) \
            .get_field("id") \
            .run(self.connection)

        try:
            id = await previous.__anext__()
        except StopAsyncIteration:
            id = None

        obb = {
            "user_id": str(member.id),
            "role_id": str(role.id),
            "server_id": str(member.guild.id)
        }
        if id:
            obb["id"] = id

        return await r.table("roleme_colours") \
            .insert(obb, conflict="update", return_changes=True) \
            .run(self.connection)

    # endregion

    # region Internals
    async def get_info(self) -> dict:
        """
        :return: Stats about the current cluster.
        """
        serv_info = await (await r.db("rethinkdb").table("server_config").run(self.connection)).next()
        cluster_stats = await r.db("rethinkdb").table("stats").get(["cluster"]).run(self.connection)

        jobs = []

        iterator = await r.db("rethinkdb").table("jobs").run(self.connection)

        while await iterator.fetch_next():
            data = await iterator.next()
            jobs.append(data)

        return {"server_info": serv_info, "stats": cluster_stats, "jobs": jobs}

        # endregion
