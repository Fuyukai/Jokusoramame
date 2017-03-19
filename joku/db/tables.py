from sqlalchemy import Column, BigInteger, Integer, DateTime, func, String, ForeignKey, Boolean, Float
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """
    A user object in the database.
    """
    __tablename__ = "user"

    #: The ID of the user.
    #: This is their snowflake ID.
    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=False,
                unique=True)

    #: The XP points of the user.
    xp = Column(Integer, nullable=False, default=0)

    #: The level of the user.
    #: This is automatically calculated.
    level = Column(Integer, nullable=False, default=1)

    #: The money of the user.
    money = Column(BigInteger, nullable=False, default=200)

    #: The last modified time of the user.
    last_modified = Column(DateTime(), server_default=func.now())

    #: The inventory for this user.
    inventory = relationship("UserInventoryItem", lazy="joined")

    #: The OAuth2 access code.
    oauth_token = Column(JSONB, nullable=True)

    #: The stocks this user contains.
    stocks = relationship("UserStock", back_populates="user")

    def __repr__(self):
        return "<User id={} xp={} money={}>".format(self.id, self.xp, self.money)

    __str__ = __repr__


class UserInventoryItem(Base):
    """
    Represents an item in a user's inventory.
    """
    __tablename__ = "user_inv_item"

    #: The ID for this inventory item.
    id = Column(Integer, primary_key=True, autoincrement=True)

    #: The user ID for this inventory item.
    user_id = Column(BigInteger, ForeignKey('user.id'))

    #: The item ID for this inventory item.
    #: Used internally.
    item_id = Column(Integer, autoincrement=False, nullable=False)

    #: The count for this inventory item.
    count = Column(Integer, autoincrement=False, nullable=False)


class Guild(Base):
    """
    A guild object in the database.
    """
    __tablename__ = "guild"

    #: The ID of the guild.
    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=False,
                unique=True)

    #: A relationship to the rolestates.
    rolestates = relationship("RoleState", backref="guild")

    #: A relationship to the settings.
    settings = relationship("Setting", backref="guild")

    #: A relationship to the event settings.
    event_settings = relationship("EventSetting", backref="guild")

    #: A relationship to the tags.
    tags = relationship("Tag", backref="guild")

    #: An array of roleme role IDs this guild can have.
    roleme_roles = Column(ARRAY(BigInteger), nullable=True, default=[])

    #: Are stocks enabled for this guild?
    stocks_enabled = Column(Boolean, default=False)

    #: The bulletin message channel.
    bulletin_channel = Column(BigInteger, nullable=True)

    #: The bulletin message ID.
    bulletin_message = Column(BigInteger, nullable=True)

    #: The announcements channel.
    announcement_channel = Column(BigInteger, nullable=True)


class UserStock(Base):
    """
    A secondary table that represents a user and stock pair.
    """
    __tablename__ = "user__stock"

    id = Column(Integer, primary_key=True, autoincrement=True)

    #: The user ID associated with this.
    user_id = Column(BigInteger, ForeignKey("user.id"))
    user = relationship("User", lazy="joined")

    #: The stock ID associated with this.
    stock_id = Column(BigInteger, ForeignKey("stock.channel_id"))
    stock = relationship("Stock", lazy="joined")

    #: The amount of stock this user owns.
    amount = Column(Integer, nullable=False, unique=False)

    #: Did this userstock crash?
    crashed = Column(Boolean, nullable=False, default=False)

    #: What did the stock crash at?
    crashed_at = Column(Float, unique=False, nullable=False, default=0.0)

    def __repr__(self):
        return "<UserStock user_id={} stock_id={} amount={}>".format(self.user_id, self.stock_id, self.amount)


class Stock(Base):
    """
    Represents a stock in a guild.
    """
    __tablename__ = "stock"

    #: The guild ID this stokc is associated with.
    guild_id = Column(BigInteger, ForeignKey("guild.id"))
    guild = relationship("Guild", lazy="joined")

    #: The channel ID this stock is associated with.
    channel_id = Column(BigInteger, unique=True, nullable=False, primary_key=True)

    #: The current price of this stock.
    price = Column(Float, unique=False, nullable=False)

    #: The number of stocks available.
    amount = Column(Integer, unique=False, nullable=False)

    #: A relationship between the stock and UserStock table.
    users = relationship("UserStock", back_populates="stock", lazy="joined")

    def __repr__(self):
        return "<Stock channel_id={} amount={} price={}>".format(self.channel_id, self.amount, self.price)


class Tag(Base):
    """
    Represents a tag in the database.
    """
    __tablename__ = "tag"

    #: The ID of the tag.
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False,
                unique=True)

    #: The guild ID of this tag.
    guild_id = Column(BigInteger, ForeignKey("guild.id"))

    #: The user ID of this tag.
    user_id = Column(BigInteger, ForeignKey("user.id"))
    user = relationship("User", backref="tags")

    #: The name of the tag.
    name = Column(String, nullable=False, unique=False, index=True)

    #: Is this tag global?
    global_ = Column(Boolean, default=False, nullable=False)

    #: The tag content.
    content = Column(String, unique=False, nullable=False)

    #: The last modified date for this tag.
    last_modified = Column(DateTime, default=func.now())

    #: Is this tag lua-based?
    lua = Column(Boolean, default=False)


class TagAlias(Base):
    """
    Represents a tag alias.
    """
    __tablename__ = "tag_alias"

    #: The ID of the tag alias.
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False,
                unique=True)

    #: The name of the alias.
    alias_name = Column(String, nullable=False)

    #: The ID of the tag being referred to.
    tag_id = Column(Integer, ForeignKey("tag.id"))
    tag = relationship("Tag", backref="aliases")

    #: The guild ID this alias is in.
    guild_id = Column(BigInteger, ForeignKey("guild.id"))
    guild = relationship("Guild", backref="tag_aliases")

    #: The owner of this alias.
    user_id = Column(BigInteger, ForeignKey("user.id"))
    user = relationship("User", backref="aliases")


class UserColour(Base):
    """
    Stores the colour state for a user.
    """
    __tablename__ = "user_colour"

    #: The ID of this colour mapping.
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)

    #: The user ID that is represented by this colour.
    user_id = Column(BigInteger, ForeignKey("user.id"), nullable=False)
    user = relationship("User", backref="colours")

    #: The guild ID that is represented by this colour.
    guild_id = Column(BigInteger, ForeignKey("guild.id"), nullable=False)
    guild = relationship("Guild", backref="colours")

    #: The role ID that this usercolour uses.
    role_id = Column(BigInteger, nullable=False, unique=True)


class Reminder(Base):
    """
    Stores a reminder.
    """
    __tablename__ = "reminder"

    #: The ID of this reminder.
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)

    #: The user that owns this reminder.
    user_id = Column(BigInteger, ForeignKey("user.id"), nullable=False)
    user = relationship("User", backref="reminders")

    #: The channel that this reminder is in.
    channel_id = Column(BigInteger, nullable=False)

    #: Is this reminder enabled?
    enabled = Column(Boolean, default=False)

    #: The text of the reminder.
    text = Column(String)

    #: When this reminder is set at.
    reminding_at = Column(DateTime, default=func.now())


class RoleState(Base):
    """
    Represents the role state of a user.
    """
    __tablename__ = "rolestate"

    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)

    #: The user this rolestate is for.
    user_id = Column(BigInteger, ForeignKey('user.id'))
    user = relationship('User')

    #: The guild ID this rolestate is for.
    guild_id = Column(BigInteger, ForeignKey("guild.id"), nullable=False)

    #: The array of role IDs this rolestate contains.
    roles = Column(ARRAY(BigInteger), nullable=True)

    #: The nickname for this rolestate.
    nick = Column(String, nullable=True)

    def __repr__(self):
        return "<RoleState user_id={} guild_id={} nick='{}' roles={}>".format(self.user_id, self.guild_id,
                                                                              self.nick, self.roles)

    __str__ = __repr__


class Setting(Base):
    """
    A setting object in the database.
    """
    __tablename__ = "setting"

    #: The ID of the setting.
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)

    #: The name of the setting.
    name = Column(String, nullable=False, unique=False)

    #: The value of the setting.
    value = Column(JSONB, nullable=False)

    #: The guild ID this setting is in.
    guild_id = Column(BigInteger, ForeignKey("guild.id"), unique=False, nullable=False)


class EventSetting(Base):
    """
    Represents a special setting for event listeners.
    """
    __tablename__ = "event_setting"

    #: The ID of this event setting.
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)

    #: The guild ID of this event setting.
    guild_id = Column(BigInteger, ForeignKey("guild.id"))

    #: Is this setting enabled?
    enabled = Column(Boolean, nullable=False, default=False)

    #: The event this setting is for.
    event = Column(String)

    #: The message that this setting contains.
    message = Column(String, unique=False, nullable=True)

    #: The event channel that this setting is for.
    channel_id = Column(BigInteger, unique=False, nullable=False)
