"""
Common utilities shared across the bot.
"""
import typing

import datetime
import discord
import tabulate
import numpy as np
from parsedatetime import Calendar


def parse_time(time_str: str, seconds: int=True) -> typing.Union[None, int, typing.Tuple[datetime.datetime, int]]:
    """
    Parses a time.

    :param time_str: The time string to parse.
    :return: The total number of seconds between now and then.
    """
    calendar = Calendar()
    t_struct, parse_status = calendar.parse(time_str)

    if parse_status == 0:
        return None

    dt = datetime.datetime(*t_struct[:6])

    diff = np.ceil((dt - datetime.datetime.utcnow()).total_seconds())
    if seconds:
        return diff
    else:
        return dt, diff


def get_role(guild: discord.Guild, role_id: int) -> discord.Role:
    return discord.utils.get(guild.roles, id=role_id)


def calculate_server_shard(guild: discord.Guild, shard_count: int) -> int:
    """
    Calculates the shard that this server will run on with ``shard_count`` shards.

    :param server: The server to check.
    :param shard_count: The number of shards to calculate with.
    """
    if shard_count == 1:
        return 0

    return (guild.id >> 22) % shard_count


# copied from https://github.com/joferkington/oost_paper_code/blob/master/utilities.py
def is_outlier(points, thresh=3.5):
    """
    Returns a boolean array with True if points are outliers and False
    otherwise.

    Parameters:
    -----------
        points : An numobservations by numdimensions array of observations
        thresh : The modified z-score to use as a threshold. Observations with
            a modified z-score (based on the median absolute deviation) greater
            than this value will be classified as outliers.

    Returns:
    --------
        mask : A numobservations-length boolean array.

    References:
    ----------
        Boris Iglewicz and David Hoaglin (1993), "Volume 16: How to Detect and
        Handle Outliers", The ASQC Basic References in Quality Control:
        Statistical Techniques, Edward F. Mykytka, Ph.D., Editor.
    """
    if len(points.shape) == 1:
        points = points[:, None]
    median = np.median(points, axis=0)
    diff = np.sum((points - median) ** 2, axis=-1)
    diff = np.sqrt(diff)
    med_abs_deviation = np.median(diff)

    modified_z_score = 0.6745 * diff / med_abs_deviation

    return modified_z_score > thresh


def reject_outliers(data, m=2):
    """
    Rejects outliers from a numpy array.
    """
    c = np.where(is_outlier(data, thresh=m), np.zeros(len(data), dtype=np.int8), data)
    return c[c != 0]


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
