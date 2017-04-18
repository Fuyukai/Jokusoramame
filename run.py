"""
Bot launcher.

This class is responsible for bootstrapping the bot.
"""
import gyukutai
gyukutai.apply()

import os
import shutil
import sys

from joku.core.bot import Jokusoramame


def main():
    # Read in the config file.
    try:
        config = sys.argv[1]
    except IndexError:
        config = "config.yml"

    if not os.path.exists(config):
        shutil.copy("config.example.yml", config)

    bot = Jokusoramame(config_file=config)
    bot.logger.info("Launching Jokusoramame in autosharded mode...")
    try:
        bot.run()
    except (KeyboardInterrupt, EOFError):
        pass

    # fuck off forever
    bot.loop.set_exception_handler(lambda *args, **kwargs: None)

if __name__ == "__main__":
    main()
