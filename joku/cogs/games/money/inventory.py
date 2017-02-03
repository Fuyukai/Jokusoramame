"""
Inventory stuff.
"""
import abc
import random

import typing

from joku.bot import Context


def get_item_by_id(id: int) -> 'BaseItem':
    """
    Gets an item by ID.
    """
    for item in globals().values():
        try:
            if issubclass(item, BaseItem):
                if item.id == id:
                    return item
        except TypeError:
            # abc caches ???
            continue


def get_item_by_name(name: str) -> typing.Type['BaseItem']:
    """
    Gets an item by name.
    """
    for item in globals().values():
        try:
            if issubclass(item, BaseItem):
                if isinstance(item.name, str) and item.name.lower() == name.lower():
                    return item
        except TypeError:
            # abc caches ???
            continue


class BaseItem(abc.ABC):
    """
    Represents an item that can be used, or similar.
    """

    @abc.abstractproperty
    def id(self):
        """
        :return: The ID of this item.
        """

    @abc.abstractproperty
    def name(self):
        """
        :return: The name of this item.
        """

    @abc.abstractproperty
    def default_buy_price(self) -> int:
        """
        :return: The default price to buy this at.
        """

    @abc.abstractproperty
    def default_sell_price(self) -> int:
        """
        :return: The default price to sell this at.
        """

    def __init__(self, ctx: Context):
        # The context this item was made with.
        self.ctx = ctx
        self.rng = random.SystemRandom()

    def get_user(self) -> dict:
        """
        :return: The current user's ID.
        """
        return self.ctx.bot.database.create_or_get_user(self.ctx.author)

    async def buy_for_price(self, price: int):
        """
        Buys this item.
        """
        await self.ctx.bot.database.update_user_currency(self.ctx.author, -price)
        await self.ctx.bot.database.add_item_to_inventory(self.ctx.author, self.id)

    async def sell_for_price(self, price: int):
        await self.ctx.bot.database.update_user_currency(self.ctx.author, price)
        await self.ctx.bot.database.remove_item_from_inventory(self.ctx.author, self.id)

    async def buy(self):
        price = self.default_buy_price

        user = await self.get_user()
        if user["currency"] < price:
            return None

        await self.buy_for_price(price)
        return price

    async def sell(self):
        price = self.default_sell_price

        user = await self.get_user()
        if user["currency"] < price:
            return None

        await self.sell_for_price(price)
        return price

    @abc.abstractmethod
    async def use(self, *args):
        """
        Implemented in subclasses to use the item.
        """


class Worker(BaseItem):
    id = 1
    name = "Oppressed Worker"

    @property
    def default_buy_price(self):
        return random.randint(10, 21)

    @property
    def default_sell_price(self):
        return random.randint(1, 4)

    async def use(self, *args):
        # RNG
        action = self.rng.uniform(0, 10)

        # Rebel
        if 0.0 <= action <= 1.0:
            # you lose 50
            await self.sell_for_price(-50)
            await self.ctx.send("\u262d A worker rebelled and took off with `§50`.")
        elif 1.0 <= action <= 8.0:
            count = await self.ctx.bot.database.get_user_item_count(self.ctx.author, self.id)
            amount = self.rng.randint(count, count * 3)
            await self.ctx.bot.database.update_user_currency(self.ctx.author, amount)
            await self.ctx.send(":pick: Your workers make you `§{}`.".format(amount))
        else:
            # ded
            await self.sell_for_price(0)
            await self.ctx.send(":skull_and_crossbones: A worker died.")
