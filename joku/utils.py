"""
Common utilities shared across the bot.
"""
import typing

import tabulate


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
