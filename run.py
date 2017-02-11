"""
Bot launcher.

This class is responsible for bootstrapping the bot.
"""
import os
import sys
import shutil

from ruamel import yaml

from joku.bot import Jokusoramame


def main():
    # Read in the config file.
    try:
        config = sys.argv[1]
    except IndexError:
        config = "config.yml"

    if not os.path.exists(config):
        shutil.copy("config.example.yml", config)

    with open(config) as f:
        config_data = yaml.load(f, Loader=yaml.Loader)

    bot = Jokusoramame(config=config_data)
    bot.logger.info("Launching Jokusoramame in autosharded mode...")
    bot.run()

if __name__ == "__main__":
    main()
