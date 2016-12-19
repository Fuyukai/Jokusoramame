"""
A RethinkDB database interface.
"""
import datetime
import random
import typing

import discord
import logbook
import rethinkdb as r
import pytz
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

    async def _reql_safe(self, awaitable):
        """
        Runs a REQL operation, but ignoring r.RuntimeError.
        """
        try:
            res = await awaitable.run(self.connection)
        except (r.ReqlRuntimeError, r.ReqlOpFailedError) as e:
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

        # Create indexes.
        await self._reql_safe(r.table("settings").index_create("server_id"))
        await self._reql_safe(r.table("users").index_create("user_id"))
        await self._reql_safe(r.table("tags").index_create("server_id"))
        await self._reql_safe(r.table("todos").index_create("user_id"))
        await self._reql_safe(r.table("reminders").index_create("user_id"))

    async def connect(self, **connection_settings):
        """
        Connects the adapter.
        """
        self.connection = await r.connect(**connection_settings)
        await self._setup()

    # Helpers
    async def to_list(self, cursor) -> list:
        """
        Gets all items from an AsyncioCursor.
        """
        l = []
        while await cursor.fetch_next():
            l.append(await cursor.next())

        return l

    # Generic actions
    async def create_or_get_user(self, user: discord.User) -> dict:
        iterator = await r.table("users").get_all(user.id, index="user_id").run(self.connection)

        exists = await iterator.fetch_next()
        if not exists:
            # Create a new user.
            return {
                "user_id": user.id,
                "xp": 0,
                "rep": 0,
                "currency": 200,
                "level": 1
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
        ids = [u.id for u in users]

        # Do a get_all using the ids as the items.
        _q = r.table("users").get_all(*ids, index="user_id")
        if order_by is None:
            iterator = await _q.run(self.connection)
            users = await self.to_list(iterator)
        else:
            iterator = await _q.order_by(order_by).run(self.connection)
            users = iterator

        return users

    # Tags
    async def get_all_tags_for_server(self, server: discord.Server):
        """
        Returns all tags for a server
        """
        iterator = await r.table("tags") \
            .get_all(server.id, index="server_id").run(self.connection)

        exists = iterator.fetch_next()
        if not exists:
            return None

        tags = []
        while await iterator.fetch_next():
            tags.append(await iterator.next())
        return tags

    async def get_tag(self, server: discord.Server, name: str):
        """
        Gets a tag from the database.
        """
        iterator = await r.table("tags") \
            .get_all(server.id, index="server_id") \
            .filter({"name": name}).run(self.connection)

        exists = await iterator.fetch_next()
        if not exists:
            return None

        tag = await iterator.next()

        return tag

    async def save_tag(self, server: discord.Server, name: str, content: str, *, owner: discord.User = None):
        """
        Saves a tag to the database.

        Will overwrite the tag if applicable.
        """
        if isinstance(owner, discord.User):
            owner_id = owner.id
        else:
            owner_id = owner

        current_tag = await self.get_tag(server, name)
        if current_tag is None:
            d = {
                "name": name,
                "content": content,
                "owner_id": owner_id if owner_id else None,
                "server_id": server.id,
                "last_modified": datetime.datetime.now(tz=pytz.timezone("UTC"))
            }

        else:
            # Edit the current_tag dict with the new data.
            d = current_tag
            d["content"] = content
            d["last_modified"] = datetime.datetime.now(tz=pytz.timezone("UTC"))

        d = await r.table("tags") \
            .insert(d, conflict="update") \
            .run(self.connection)

        return d

    async def delete_tag(self, server: discord.Server, name: str):
        """
        Deletes a tag.
        """
        d = await r.table("tags") \
            .get_all(server.id, index="server_id") \
            .filter({"name": name}) \
            .delete() \
            .run(self.connection)

        return d

    # XP

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
            added = random.randint(1, 3)

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

    # Currency

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

    async def get_user_currency(self, user: discord.User) -> dict:
        """
        Gets the user's current currency.
        """
        user_dict = await self.create_or_get_user(user)

        return user_dict.get("currency", 200)

    # Settings

    async def set_setting(self, server: discord.Server, setting_name: str, **values: dict) -> dict:
        """
        Sets a setting.
        :param server: The server to set the setting in.
        :param setting_name: The name to use.
        :param values: The values to insert into the settings.
        """
        # Try and find the ID.
        setting = await self.get_setting(server, setting_name)
        if not setting:
            d = {"server_id": server.id, "name": setting_name, **values}
        else:
            # Use the ID we have.
            d = {"server_id": server.id, "name": setting_name, "id": setting["id"], **values}

        d = await r.table("settings") \
            .insert(d, conflict="update") \
            .run(self.connection)

        return d

    async def get_setting(self, server: discord.Server, setting_name: str) -> dict:
        """
        Gets a setting from RethinkDB.
        :param server: The server to get the setting from.
        :param setting_name: The name to retrieve.
        """
        d = await r.table("settings") \
            .get_all(server.id, index="server_id") \
            .filter({"name": setting_name}) \
            .run(self.connection)

        # Only fetch one.
        # There should only be one, anyway.
        fetched = await d.fetch_next()
        if not fetched:
            return None

        i = await d.next()
        return i

    async def get_event_message(self, server: discord.Server, event: str, default: str = "") \
            -> typing.Tuple[discord.Channel, str]:
        """
        Gets an event message, if the event exists.
        """
        enabled = await self.get_setting(server, "events")
        if not enabled:
            return

        events = enabled.get("events", {})
        if not events.get(event):
            return

        channel = server.get_channel(events[event])
        if not channel:
            return

        message = await r.table("settings") \
            .get_all(server.id, index="server_id") \
            .filter({"name": "event_msg", "event": event}) \
            .run(self.connection)

        l = await self.to_list(message)
        if not l:
            return

        message = l[0].get("msg", default)

        return [channel, message]

    # Ignores
    async def is_channel_ignored(self, channel: discord.Channel, type_: str = "levelling"):
        """
        Checks if a channel has an ignore rule on it.
        """
        cursor = await r.table("settings") \
            .get_all(channel.server.id, index="server_id") \
            .filter({"name": "ignore", "target": channel.id, "type": type_}) \
            .run(self.connection)

        items = await self.to_list(cursor=cursor)
        # Hacky thing
        # Turns a truthy value into True
        # and a falsey value ([], None) into False
        return not not items

    # TODOs

    async def get_user_todos(self, user: discord.User) -> typing.List[dict]:
        """
        Gets a list of TODO entries for a user.
        """
        items = await r.table("todos") \
            .get_all(user.id, index="user_id") \
            .order_by("priority") \
            .run(self.connection)

        return items

    async def add_user_todo(self, user: discord.User, content: str, priority: int = None):
        """
        Adds a TODO for a user.
        """
        d = {
            "user_id": user.id,
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
            .get_all(user.id, index="user_id") \
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
            .get_all(user.id, index="user_id") \
            .filter({"priority": index}) \
            .delete(return_changes=True) \
            .run(self.connection)

        # Now move all of the indexes down.
        i2 = await r.table("todos") \
            .get_all(user.id, index="user_id") \
            .filter(r.row["priority"] > index) \
            .update({"priority": r.row["priority"] - 1},
                    return_changes=True) \
            .run(self.connection)

        return [i1, i2]

    # Internals

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
