"""
A tool to convert the old RethinkDB database data to PostgreSQL data.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import rethinkdb as r

from joku.db.tables import User, Guild, UserColour, Tag, Setting

# edit to change settings
rethink_settings = {
    "host": "127.0.0.1",
    "port": 28015,
    "db": "jokusoramame"
}

# edit to change settings
postgres_dsn = "postgresql://joku@127.0.0.1/joku"

# Connect to Postgres.
engine = create_engine(postgres_dsn)
session_factory = sessionmaker(bind=engine)
session = session_factory()  # type: Session
print("Connected to postgres on {}.".format(postgres_dsn))

# Connect to rethinkdb in REPL mode.
connection = r.connect(**rethink_settings).repl()
print("Connected to RethinkDB with settings {}.".format(rethink_settings))

print("You MUST have a clean PostgreSQL database before running this tool. Migrate all data? [y/N] ", end="")
x = input()
if x.lower() != "y":
    raise SystemExit(1)

# Guild object cache
guilds = {}

# User object cache
users = {}


def get_or_create_guild(id: int):
    try:
        return guilds[id]
    except KeyError:
        g = Guild(id=id)
        guilds[id] = g
        return g


def get_or_create_user(id: int):
    try:
        return users[id]
    except KeyError:
        u = User(id=id)
        users[id] = u
        return u

with session.no_autoflush:
    # First thing, create all the user objects.
    r_users = r.table("users").run()
    for user in r_users:
        user_id = user["user_id"]

        print("Migrating user {}...".format(user["user_id"]))
        user["xp"] = min(max(0, user["xp"]), 2 ** 16 - 1)
        user["level"] = min(max(0, user["level"]), 2 ** 16 - 1)
        obb = get_or_create_user(int(user_id))
        obb.xp = user["xp"]
        obb.level = user["level"]

    # Create all of the guild objects and add the roleme roles to them.
    roleme = r.table("roleme_roles").run()
    for guild in roleme:
        g = get_or_create_guild(int(guild["server_id"]))
        g.roleme_roles = [int(r_id) for r_id in guild["roles"]]
        # update the guild cache
        print("Created roleme for {}.".format(g.id))

    # Create all of the colourme roles.
    colourme = r.table("roleme_colours").run()
    roles = set()
    for obb in colourme:
        u = get_or_create_user(int(obb["user_id"]))
        g = get_or_create_guild(int(obb["server_id"]))

        if u.id in [x.user_id for x in session.new if isinstance(x, UserColour)]:
            continue

        ob = UserColour()
        ob.user_id = u.id
        ob.guild_id = g.id
        ob.role_id = int(obb["role_id"])

        roles.add(ob.role_id)
        print("Migrated colourme for {}|{}|{}".format(ob.user_id, ob.guild_id, ob.role_id))

        session.add(ob)

    # Create all of the tags.
    for obb in r.table("tags").run():
        try:
            u = get_or_create_user(int(obb["owner_id"]))
            g = get_or_create_guild(int(obb["server_id"]))
        except KeyError as e:
            print("Bad key: {}".format(e))
            print(obb)
            continue

        t = Tag()
        t.user_id = u.id
        t.guild_id = g.id
        t.name = obb["name"]
        t.content = obb["content"]

        session.merge(t)
        print("Migrated tag {}|{}.".format(t.name, t.guild_id))

    [session.merge(user) for user in users.values()]
    [session.merge(guild) for guild in guilds.values()]

    _us = len([x for x in session.new if isinstance(x, User)])
    _gs = len([x for x in session.new if isinstance(x, Guild)])

    print("Adding in {}|{} user objects and {}|{} guild objects.".format(_us, len(users), _gs, len(guilds)))
    print("All objects added to session! Committing to database (this may take some time...)")
    session.commit()
    print("All data migrated.")
