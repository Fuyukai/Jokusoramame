# Jokusoramame (Juck Fava)

[![Join the Discord!](https://discordapp.com/api/guilds/237980238536114176/widget.png)](https://discord.gg/uQwVat8)

[Add the bot to your server!](https://discordapp.com/oauth2/authorize?client_id=235114171270823936&scope=bot)
 
Jokusoramame is Yet Another General Purpose Bot (TM)

## Setting up the bot environment

You will need:

 - Python 3.5.2+
 - Postgres 9.x or higher
 - Redis 3.x.x or higher

### Installation steps

1. **Install `pipenv`.**

    Pipenv is the tool used to create and manage the virtual package
    environment for the bot. It is available on PyPI:

     `pip install pipenv`

2. **Setup the virtual environment.**

    To create a virtual environment, invoke `pipenv` with the `--three`
    option.

     `pipenv --three`

3. **Install the dependencies.**

    Jokusoramame is a complex bot, and as such has a lot of
    dependencies. To install them all, use Pipenv.

     `pipenv install`

    This will require a **C compiler** and the **Python development
    headers** to compile the mathematics libraries used.

4. **Install discord.py rewrite.**

    Pipenv doesn't support git dependencies properly, so needs a manual
    install for discord.py.

     `pipenv run pip install -U git+https://github.com/Rapptz/discord.py@rewrite#egg=discord.py`

5. **Create a database in PostgreSQL.**

    For security, it is recommended you create a special user with a
    password.

     ```sql
     CREATE ROLE joku WITH LOGIN PASSWORD 'botpw';
     CREATE DATABASE joku OWNER joku;
     ```

    This will create a new database that the bot can modify.

    You will also want to switch to the database and create the `hstore`
    extension.

    ```sql
    CREATE EXTENSION hstore;
    ```

    This cannot be automatically created as it requires a superuser.

6. **Run the migrations.**

    The migration scripts upgrade the database to the latest version.

     `pipenv run alembic upgrade HEAD`

7. **Copy and edit the config file.**

     `cp config.example.yml config.yml`

    Then edit the config file and provide these values at a minimum:

     - `bot_token`
     - `dsn`

8. **Boot the bot.**

    The provided `start.sh` script will automatically boot the bot for
    you.

     `./start.sh`

    Once loaded, the bot will print the invite URL and automatically
    assign you as the bot owner.

### Development

Once following the above steps, you can enter the virtual environment
created by Pipenv with `pipenv shell`, or run commands with
`pipenv run`.
