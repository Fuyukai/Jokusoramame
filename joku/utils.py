"""
Common utilities shared across the bot.
"""
import typing

import discord
import tabulate
import numpy as np


def get_role(guild: discord.Guild, role_id: int) -> discord.Role:
    return discord.utils.get(guild.roles, id=role_id)


def get_index(cbl, item: typing.Iterable):
    for num, _ in enumerate(item):
        if cbl(_):
            return num


def calculate_server_shard(guild: discord.Guild, shard_count: int) -> int:
    """
    Calculates the shard that this server will run on with ``shard_count`` shards.

    :param server: The server to check.
    :param shard_count: The number of shards to calculate with.
    """
    if shard_count == 1:
        return 0

    return (guild.id >> 22) % shard_count


def reject_outliers(data, m=2):
    """
    Rejects outliers from a numpy array.
    """
    first = np.where(abs(data - np.mean(data)) < m * np.std(data), data, np.zeros(len(data), dtype=np.int8))
    # pass around again
    return np.where(abs(first - np.mean(first)) < m * np.std(first), first, np.zeros(len(first), dtype=np.int8))


def paginate_large_message(message: str, use_codeblocks: bool = True) -> typing.List[str]:
    """
    Paginates a large message, delimited by code blocks.

    :param message: The message to paginate.
    :return: A list of message pages.
    """
    pages = []
    current_message = message

    while True:
        # 1993 - used for ``` and ```.
        if len(current_message) < 1993:
            # Add it to pages, and break.
            if use_codeblocks:
                pages.append("```{}```".format(current_message))
            else:
                pages.append(current_message)
            break

        # Get the first 1993 chars from it, and reset current_message.
        new_message, current_message = current_message[:1993], current_message[1993:]
        if use_codeblocks:
            pages.append("```{}```".format(new_message))
        else:
            pages.append(new_message)

    # Return the list of pages.
    return pages


def paginate_table(rows: list, headers: typing.Iterable, table_format="orgtbl",
                   limit=2000) -> typing.List[str]:
    """
    Paginates a table into multiple messages, each fitting into the 2000 char limit Discord provides.

    :param rows: An iterable of rows to paginate.
    :param headers: The headers to use for the table.
    :param table_format: The format of the table to produce.
    :param limit: The cutoff for tables.
    :return: A list of formatted tables.
    """

    pages = []

    current_rows = []

    while True:
        # No more rows to fetch.
        if not rows:
            break
        # Fetch the next row off of the list.
        current_row = rows[0]
        # Add it to the current rows.
        current_rows.append(current_row)
        # Attempt to render the table, so we can check if it's above the length limit.
        # If it is, remove this row from the list, add the current rendered table to pages.
        # Then insert this to the front of the rows, which will make it re-try wth the next page.
        _tbl = tabulate.tabulate(current_rows, headers=headers, tablefmt=table_format)
        fmtted = "```{}```".format(_tbl)
        if len(fmtted) >= limit:
            # We've reached too many rows, remove one, render the table, and store it.
            current_rows = current_rows[:-1]
            # Restore the current row to the rows list, which will be used again in the next loop iteration.
            _tbl = tabulate.tabulate(current_rows, headers=headers, tablefmt=table_format)
            fmtted = "```{}```".format(_tbl)
            pages.append(fmtted)
            # Reset current_rows.
            current_rows = []
            continue
        # Otherwise, the table isn't too big.
        # We can continue adding rows to this.
        rows.pop(0)

    # Add the current table to the pages, too.
    _tbl = tabulate.tabulate(current_rows, headers=headers, tablefmt=table_format)
    fmtted = "```{}```".format(_tbl)
    pages.append(fmtted)

    return pages
