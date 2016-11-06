"""
The thread manager is the manager for the bot shards.
"""
import functools
import os
import shutil
import sys
import collections

import asyncio
import requests
import threading

import time
from discord.http import HTTPClient
from logbook import Logger
from ruamel import yaml

from joku import VERSION
from joku.bot import Jokusoramame


class ManagerLocal(threading.local):
    """
    The thread-local class for the manager.
    """
    bot = None


class Manager(object):
    def __init__(self):
        self.threads = {}

        # The list of bots.
        self.bots = {}

        self.max_shards = 0

        self.logger = Logger("Jokusoramame.ThreadManager")

        self._last_stats_upload = 0

        # The events counter.
        self.events = collections.Counter()

    def _start_in_thread(self, id: int, func: callable):
        t = threading.Thread(target=func)
        self.threads[id] = t

        t.start()

        return t

    def watch_threads(self):
        while True:
            # Sleep for 2s between each thread.
            for index, thread in self.threads.copy().items():
                if not thread.is_alive():
                    self.logger.warning("Thread {} crashed, rebooting it.".format(index))
                    # Reboot the thread.
                    self.threads.pop(index)
                    self.create_thread(index)

                time.sleep(2)

    def _run_bot_threaded(self, shard_id: int):
        """
        Runs the brunt of the work.

        This is ran inside a thread.
        """
        policy = asyncio.get_event_loop_policy()
        # Create a new thread-local event loop.
        loop = policy.new_event_loop()  # type: asyncio.BaseEventLoop
        policy.set_event_loop(loop)

        # Make a new bot instance.
        bot = Jokusoramame(config=self.config, shard_id=shard_id, shard_count=self.max_shards, manager=self,
                           loop=loop)
        # Login with the bot.
        loop.run_until_complete(bot.login())
        self.bots[shard_id] = bot
        ManagerLocal.bot = bot

        try:
            loop.run_until_complete(bot.connect())
        except:
            loop.run_until_complete(bot.logout())
        finally:
            loop.close()

    def kill_all_threads(self):
        for bot in self.bots.values():
            # Kill it.
            self.logger.info("Killing bot {}.".format(bot.shard_id))
            bot.loop.stop()
            bot.die()

        # Join each thread.
        for thread in self.threads.values():
            thread.join()

    def create_thread(self, index: int):
        """
        Creates a new shard thread.
        """
        partial = functools.partial(self._run_bot_threaded, shard_id=index)
        t = self._start_in_thread(index, partial)

        return t

    def start_all(self):
        """
        Starts all the bots.
        """
        self.logger.info("Loading Jokusoramame, version {}.".format(VERSION))
        # Load the config
        try:
            cfg = sys.argv[1]
        except IndexError:
            cfg = "config.yml"

        # Copy the default config file.
        if not os.path.exists(cfg):
            shutil.copy("config.example.yml", cfg)
            self.logger.error("Could not find default config file - copied new one, please edit and restart the bot.")
            return

        with open(cfg) as f:
            self.config = yaml.load(f)

        # Check if dev mode.
        if self.config.get("developer_mode", False):
            self.max_shards = 1
            self.logger.info("Starting single-shard instance of the bot.")
            # Run the stats uploader in a loop anyway.
            self._run_bot_threaded(0)
            return

        token = self.config["bot_token"]

        # Get the shards endpoint.
        endpoint = HTTPClient.GATEWAY + "/bot"

        r = requests.get(endpoint, headers={"Authorization": "Bot {}".format(token)})

        if r.status_code != 200:
            self.logger.error("Unable to download number of shards - is your token correct?")
            return

        number_of_shards = r.json()["shards"]
        number_of_shards += 1
        self.max_shards = number_of_shards

        # Create a bunch of threads, one for each shard.
        for x in range(0, number_of_shards):
            self.create_thread(x)

        try:
            self.watch_threads()
        except KeyboardInterrupt:
            self.kill_all_threads()

    def get_server(self, server_id: str):
        """
        Helper function to get a server.
        """
        for server in self.get_all_servers():
            if server.id == server_id:
                return server

        return None

    def get_all_members(self):
        """
        Helper function to get all members across all shards.
        """
        for bot in self.bots.values():
            yield from bot.get_all_members()

    @property
    def unique_member_count(self):
        return len({x.id for x in self.get_all_members()})

    def get_all_servers(self):
        """
        Helper function to get all servers across all shards.
        """
        for bot in self.bots.values():
            for server in bot.servers:
                yield server

    def get_all_channels(self):
        """
        Helper function to get all channels across all shards.
        """
        for bot in self.bots.values():
            yield from bot.get_all_channels()
