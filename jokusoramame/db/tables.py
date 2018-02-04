"""
Contains database definitions.
"""
from asyncqlio import BigInt, Column, Integer, Serial, Text, table_base

Table = table_base(name="Table")


class UserXP(Table, table_name="user_xp"):
    """
    Represents a user's XP in a guild.
    """
    #: The ID of this XP.
    id = Column(Serial(), primary_key=True)

    #: The user ID for this XP.
    user_id = Column(BigInt(), nullable=False)

    #: The guild ID this XP is associated with.
    guild_id = Column(BigInt(), unique=False, nullable=False)

    #: The amount of XP this user has.
    xp = Column(Integer(), unique=False, nullable=False, default=0)

    #: The level for this user.
    level = Column(Integer(), unique=False, nullable=False, default=1)


class GuildSetting(Table, table_name="guild_setting"):
    """
    Represents a guild setting.
    """
    #: The ID of this setting.
    id = Column(Serial(), primary_key=True)

    #: The guild ID for this setting.
    guild_id = Column(BigInt(), unique=False, nullable=False)

    #: The name of this setting.
    name = Column(Text(), unique=False, nullable=False)

    #: The value of this setting.
    value = Column(Text(), unique=False, nullable=False)


class Rolestate(Table, table_name="rolestate"):
    """
    Represents a rolestate.
    """
    #: The ID of this rolestate.
    id = Column(Serial(), primary_key=True)

    #: The user ID that the rolestate is registered for.
    user_id = Column(BigInt(), nullable=False)

    #: The guild ID this rolestate is registered in.
    guild_id = Column(BigInt(), nullable=False)

    #: A comma-separated list of role IDs for this rolestate.
    #: TODO: Array support.
    roles = Column(Text(), nullable=False)

    #: The stored nickname for this rolestate.
    nick = Column(Text(), nullable=False)
