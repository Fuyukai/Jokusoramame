import random

from curious.commands import Plugin, command, Context


money = '**{0} :̶.̶|̶:̶;̶**'

BAD_RESPONSES = [
    f'haha nerd u lost {money}'
]

GOOD_RESPONSES = [
    f'wowe.... {money}'
]


class Gambling(Plugin):
    """
    Plugin for gambling related commands.

    U better thank me...
    """

    @command()
    async def raffle(self, ctx: Context, price: int = 5):
        # TODO docstring
        # TODO cooldown
        # TODO database stuffs

        balance = 28364819723648712365987123  # TODO

        price = max(price, 5)  # No mercy for the "hahaha I am very sneaky" user

        if balance < 0:
            # vintage
            await ctx.channel.messages.send(
                '\N{DRAGON} A debt collector came and broke your knees. '
                'You are now free of debt.'
            )
            # TODO give person 5 money

        if balance < price:
            return await ctx.channel.messages.send("\N{CROSS MARK} Don't gamble with money you don't have, dum-dum...")

        # TODO weighted rng
        amount = random.randint(-100, 100)

        if amount < 0:
            response = random.choice(BAD_RESPONSES)
        else:
            response = random.choice(GOOD_RESPONSES)

        await ctx.channel.messages.send(response.format(abs(amount)))
