"""
OAuth dance part of the bot.
"""
import asyncio
import functools
import json
import os

import typing

import discord
from asyncio_extras import threadpool
from kyoukai.asphalt import HTTPRequestContext
from kyoukai.blueprint import Blueprint
from requests_oauthlib import OAuth2Session
from sqlalchemy.orm import Session
from werkzeug.utils import redirect
from werkzeug.wrappers import Response
import itsdangerous

from joku.bot import Jokusoramame
from joku.db.tables import User

API_BASE_URL = "https://discordapp.com/api/v6"
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = API_BASE_URL + '/oauth2/token'

API_ME_URL = API_BASE_URL + '/users/@me'
API_GUILDS_URL = API_BASE_URL + '/users/@me/guilds'
API_INVITE_URL = API_BASE_URL + '/invite/{code}'


class OAuth2DanceHelper(object):
    """
    A class to help with the OAuth 2 dance.
    """
    SCOPES = ["identify", "guilds"]

    def __init__(self, bot: Jokusoramame):
        """
        :param bot: The bot instance. 
        """
        self.bot = bot

        if self.bot.config.get("developer_mode", False) is True:
            os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

    @property
    def client_id(self) -> int:
        """
        :return: The client ID of this bot. 
        """
        return self.bot.app_id

    @property
    def client_secret(self) -> str:
        """
        :return: The client secret of this bot. 
        """
        return self.bot.config["oauth"]["secret_key"]

    @property
    def oauth2_redirect(self) -> str:
        """
        :return: The OAuth2 redirect of this bot.
        """
        return self.bot.config["oauth"]["redirect_uri"]

    def make_session(self, token=None, state=None, scopes=None):
        """
        Makes a new OAuth2Session.
        
        :param token: The OAuth2 token to use. 
        :param state: The OAuth2 state to use.
        :param scopes: The OAuth2 scopes to use.
        """

        return OAuth2Session(
            client_id=self.client_id,
            token=token,
            state=state,
            scope=scopes,
            redirect_uri=self.oauth2_redirect,
            auto_refresh_kwargs={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
            },
            auto_refresh_url=TOKEN_URL,
            token_updater=self.token_updater)

    async def _token_updater(self, token: dict):
        """
        A callback coroutine that updates the token in the user's entry in the PostgreSQL database.
        
        :param token: The token to update. 
        """

        user = await self.bot.database.get_or_create_user(int(token["id"]))

        async with threadpool():
            with self.bot.database.get_session() as sess:
                assert isinstance(sess, Session)
                user.oauth_token = token
                sess.add(user)

        return user

    def token_updater(self, token: dict):
        """
        Callback that schedules the coroutine above.
        """
        return self.bot.loop.create_task(self._token_updater(token))

    # OAuth2 methods
    def get_redirect_url_and_state(self, scopes: typing.List[str] = None) -> typing.Tuple[str, typing.Any]:
        """
        Gets the redirect URL for a new OAuth2 request.
         
        :param scopes: The scopes to request. 
        :return: A tuple of the redirect URL and the new OAuth2 session.
        """
        scopes = scopes or self.SCOPES
        sess = self.make_session(scopes=scopes)

        url, state = sess.authorization_url(AUTHORIZATION_BASE_URL)
        return url, state

    async def fetch_token(self, state: str, code: str, url: str) -> dict:
        """
        Fetches the token for a user.
        
        This does **not** store the token.
        """
        sess = self.make_session(state=state)
        async with threadpool():
            token = sess.fetch_token(TOKEN_URL, code=code, authorization_response=url,
                                     client_secret=self.client_secret)  # oauthlib is bad and needs this

        return token

    async def get_me(self, token: dict) -> dict:
        """
        Gets the currently logged in user.
        """
        async with threadpool():
            sess = self.make_session(token=token)
            data = sess.get(API_ME_URL).json()

            # cast id to int
            data["id"] = int(data["id"])

        return data

    async def get_servers(self, token: dict) -> dict:
        """
        Gets the servers for this user.
        """
        async with threadpool():
            sess = self.make_session(token=token)
            data = sess.get(API_GUILDS_URL).json()

        return data


bp = Blueprint(name="oauth2", prefix="/oauth2")


@bp.route("/test/@me")
async def at_me(ctx: HTTPRequestContext):
    cookie = ctx.request.cookies.get("joku_user_id")
    if cookie is None:
        return redirect("/oauth2/redirect")

    try:
        uid = ctx.bot.signer.loads(cookie)
    except itsdangerous.BadData:
        r = redirect("/oauth2/redirect")
        r.delete_cookie(key="joku_user_id")
        return r

    token = (await ctx.bot.database.get_or_create_user(id=uid)).oauth_token
    return (json.dumps(await ctx.bot.oauth.get_me(token))), 200, {"Content-Type": "application/json"}


@bp.route("/test/servers")
async def test_servers(ctx: HTTPRequestContext):
    cookie = ctx.request.cookies.get("joku_user_id")
    if cookie is None:
        return redirect("/oauth2/redirect")

    try:
        uid = ctx.bot.signer.loads(cookie)
    except itsdangerous.BadData:
        r = redirect("/oauth2/redirect")
        r.delete_cookie(key="joku_user_id")
        return r

    token = (await ctx.bot.database.get_or_create_user(id=uid)).oauth_token
    return (json.dumps(await ctx.bot.oauth.get_servers(token))), 200, {"Content-Type": "application/json"}


@bp.route("/callback")
async def _callback(ctx: HTTPRequestContext):
    """
    Called to store the token in the cookies and the DB.
    """
    if "errors" in ctx.request.args:
        # redirect back to /redirect
        return redirect("/oauth2/redirect", code=302)

    state = ctx.request.args["state"]
    code = ctx.request.args["code"]

    url = ctx.request.url
    token = await ctx.bot.oauth.fetch_token(state=state, code=code, url=url)

    # Get our user object
    me = await ctx.bot.oauth.get_me(token=token)

    user = await ctx.bot.database.get_or_create_user(id=me["id"])

    async with threadpool():
        with ctx.bot.database.get_session() as sess:
            assert isinstance(sess, Session)
            user.oauth_token = token
            sess.add(user)

    signed_cookie = ctx.bot.signer.dumps(me["id"])
    response = redirect("/", code=200)
    response.set_cookie(key="joku_user_id", value=signed_cookie)

    return response


@bp.route("/redirect")
async def _redirect(ctx: HTTPRequestContext):
    """
    Redirects the user to the Discord OAuth2 signin page.
    """
    bot = ctx.bot  # type: Jokusoramame
    # get the oauth2 fuckery
    url, state = bot.oauth.get_redirect_url_and_state()
    response = redirect(url, code=302)

    return response
