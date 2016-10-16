import functools
import os
import shutil
import sys

import requests
import threading
from ruamel import yaml
from discord.http import HTTPClient

from joku import bot


def main():
    """
    Main entry point for Jokusoramame.
    """
    # Load the config
    try:
        cfg = sys.argv[1]
    except IndexError:
        cfg = "config.yml"

    # Copy the default config file.
    if not os.path.exists(cfg):
        shutil.copy("config.example.yml", cfg)

    with open(cfg) as f:
        config = yaml.load(f)

    token = config["bot_token"]

    # Get the shards endpoint.
    endpoint = HTTPClient.GATEWAY + "/bot"

    r = requests.get(endpoint, headers={"Authorization": "Bot {}".format(token)})

    number_of_shards = r.json()["shards"]

    # Create the threads required for each shard.
    threads = []
    for x in range(0, number_of_shards):
        t = threading.Thread(target=functools.partial(bot.run_threaded, x, number_of_shards))
        t.start()
        threads.append(t)

if __name__ == "__main__":
    main()
