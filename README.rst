Jokusoramame
------------

Bad bot.


Setup instructions
==================

There is zero intention for anyone but me to run the bot.

 1. Copy ``config.example.yml`` to ``config.yml`` and edit as appropriate.

 2. Run ``pipenv install`` to install the required dependencies.

 3. Setup a postgresql database and redis database and fill in the appropriate sections in the
 config file.

 4. Run ``pipenv run asql-migrate migrate HEAD``.

 5. To run the bot, do ``pipenv run python3 run.py``