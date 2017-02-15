"""
Root pages.
"""
import itsdangerous
from kyoukai.asphalt import HTTPRequestContext
from kyoukai.blueprint import Blueprint
from werkzeug.utils import redirect
from werkzeug.wrappers import Response

from joku.core.bot import Jokusoramame
from joku.web.tmpl import render_template

root = Blueprint("root")


@root.before_request
async def add_user(ctx: HTTPRequestContext):
    # add the user object to the ctx
    bot = ctx.bot  # type: Jokusoramame

    cookie = ctx.request.cookies.get("joku_user_id")
    if cookie is None:
        # allow null cookies
        ctx.user = None
        return ctx

    try:
        uid = ctx.bot.signer.loads(cookie)
    except itsdangerous.BadData:
        # force a re-authorization
        r = redirect("/oauth2/redirect")
        r.delete_cookie(key="joku_user_id")
        raise r

    user = await bot.database.get_or_create_user(id=uid)
    ctx.user = user
    return ctx


@root.after_request
async def after(ctx: HTTPRequestContext, result: Response):
    # all requests here are HTML
    result.headers["Content-Type"] = "text/html; charset=utf-8"
    return result


@root.route("/")
async def index(ctx: HTTPRequestContext):
    return await render_template("index.html", ctx=ctx)
