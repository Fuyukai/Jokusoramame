import logging
import os
import shutil
import sys
from ruamel import yaml

import curio
import multio
import traceback
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


def main():
    multio.init('curio')

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
