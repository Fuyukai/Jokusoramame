import logging
import os
import shutil
import sys
import traceback
from ruamel import yaml

import curio
import multio
from curio import TaskError
from curious.exc import Unauthorized
from logbook import StreamHandler
from logbook.compat import redirect_logging

from jokusoramame.bot import Jokusoramame
from jokusoramame.utils import loop

# logging

redirect_logging()
StreamHandler(sys.stderr).push_application()
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger("cuiows").setLevel(logging.ERROR)

# misc setup of modules
import matplotlib; matplotlib.use('Agg')  # use Agg for no-GUI mode
multio.init('curio')  # use curio for our async backend
import seaborn; seaborn.set(color_codes=True)  # enable seaborn colour codes
seaborn.set_style("whitegrid")  # change seaborn style
seaborn.set_palette(seaborn.color_palette("cubehelix", 16))  # change seaborn palette


def main():
    if not os.path.exists("config.yml"):
        shutil.copy("config.example.yml", "config.yml")
        print("Copied config.example.yml to config.yml")
        return

    with open("config.yml") as f:
        config = yaml.load(f, Loader=yaml.Loader)

    bot = Jokusoramame(config)
    try:
        bot.run()
    except TaskError as e:
        if type(e.__cause__) == Unauthorized:
            logging.getLogger("Jokusoramame").error("Invalid token passed")
        elif type(e.__cause__) == curio.TaskGroupError:
            error = e.__cause__
            for task in error.failed:
                if task.next_exc is not None:
                    traceback.print_exception(None, task.next_exc, task.next_exc.__traceback__)

    finally:
        curio.run(loop.shutdown())


if __name__ == '__main__':
    main()
