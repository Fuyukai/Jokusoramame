"""
This is cancer.

Why did I do this?
"""
import asyncio
import functools

import discord
import time
import youtube_dl
from discord.ext import commands
from math import floor

from joku.bot import Jokusoramame


class MusicInstance:
    """
    Wraps an instance of a Music player.
    """

    def __init__(self, server: discord.Server):
        self.queue = asyncio.Queue()

        self.player_task = None

        # The current start time, used for playing time
        self.current_song_start_time = 0

        # When to reset the queue.
        self.queue_continue_event = asyncio.Event()

        self.lock = asyncio.Lock()

        # The current voice client.
        self.voice_client = None

        # The current player.
        self.player = None

        # If this player is playing.
        self.playing = False

        # The current information about this track.
        self.current_info = {}

    async def disconnect(self):
        """
        Disconnects the current voice player.
        """
        self.player_task.cancel()
        self.player.stop()

        try:
            await self.voice_client.disconnect()
            # Manually send a VOICE_STATE_UPDATE.
            await self.voice_client.main_ws.voice_state(self.voice_client.guild_id, None, self_mute=True)
        except Exception:
            # o well
            pass

        return

    async def download_information(self, ctx, video_url: str, echo: bool = True):
        """
        Downloads video information.
        """
        async with self.lock:
            if echo:
                await ctx.bot.send_message(ctx.message.channel, ":hourglass: Downloading video information...")

            ydl = youtube_dl.YoutubeDL({
                "format": 'best', "ignoreerrors": True,
                "default_search": "ytsearch", "source_address": "0.0.0.0"
            })
            func = functools.partial(ydl.extract_info, video_url, download=False)

            # Run it in an executor.
            data = await ctx.bot.loop.run_in_executor(None, func)

        return data

    def construct_voice_data(self, track_dict: list, is_playlist: bool):
        """
        Adds voice data to the queue.
        """
        counter = 0
        for item in track_dict:
            self.queue.put_nowait(item)
            counter += 1

        return counter

    async def ensure_voice_connected(self, ctx, channel: discord.Channel):
        """
        Ensures voice is connected.
        """
        voice_client = ctx.bot.voice_client_in(ctx.message.server)  # type: discord.VoiceClient
        if voice_client is None:
            try:
                voice_client = await ctx.bot.join_voice_channel(channel=channel)
            except (discord.ClientException, TimeoutError, asyncio.TimeoutError):
                await ctx.bot.send_message(ctx.message.channel, ":x: Unable to join voice channel.")
                return None
        else:
            # Check if we're connected anyway.
            # This works around some weird bugs.
            if not voice_client.is_connected():
                # Since we're not, delete the voice client and re-try.
                try:
                    del ctx.bot.connection._voice_clients[ctx.message.server.id]
                except Exception:
                    # lol what
                    pass

                # Now, reconnect.

                try:
                    voice_client = await ctx.bot.join_voice_channel(channel=channel)
                except (discord.ClientException, TimeoutError, asyncio.TimeoutError):
                    await ctx.bot.send_message(ctx.message.channel, ":x: Unable to join voice channel.")
                    return None

        return voice_client

    async def run(self, ctx):
        while True:
            # Reset the event.
            self.queue_continue_event.clear()
            # Get the data off of the queue.
            data = await self.queue.get()
            # Re-download the video info anyway lol
            webpage_url = data.get("webpage_url")
            self.current_info = await self.download_information(ctx, webpage_url, False)
            if not self.current_info.get("duration"):
                self.current_info["duration"] = 0

            # Ok, now actually play.
            download_url = self.current_info.get("url")

            self.player = self.voice_client.create_ffmpeg_player(download_url, after=self.queue_continue_event.set)
            self.player.start()
            self.playing = True

            self.current_song_start_time = time.time()

            await ctx.bot.send_message(ctx.message.channel, "**:heavy_check_mark: Now playing:** {}".format(
                self.current_info.get("title")))

            await self.queue_continue_event.wait()

            # Reset stuff.
            self.player = None
            self.playing = False


class Music(object):
    def __init__(self, bot: Jokusoramame):
        self.bot = bot

        self.musics = {}

    def get_server_music(self, server: discord.Server) -> MusicInstance:
        if server.id not in self.musics:
            self.musics[server.id] = MusicInstance(server)

        return self.musics[server.id]

    @commands.command(pass_context=True, aliases=["nowplaying"])
    async def np(self, ctx):
        """
        Gets the currently playing track.
        """
        m = self.get_server_music(ctx.message.server)
        if not m.playing:
            await self.bot.say("**Not currently playing any tracks.**")
            return

        title = m.current_info.get("title")
        # Get the elapsed time.
        elapsed_time = time.time() - m.current_song_start_time
        # Divide elapsed time into minutes and seconds.
        m1, s1 = divmod(elapsed_time, 60)
        # Divide current duration into minutes and seconds.
        m2, s2 = divmod(m.current_info.get("duration"), 60)

        # If m2 and s2 are 0, it's probably live.
        if m2 == 0 and s2 == 0:
            fmt = "[LIVE]"
        else:
            m1, m2, s1, s2 = floor(m1), floor(m2), floor(s1), floor(s2)
            fmt = "[{:02d}:{:02d}/{:02d}:{:02d}]".format(m1, s1, m2, s2)

        await self.bot.say("Currently playing: `{}` `{}`".format(title, fmt))

    @commands.command(pass_context=True)
    async def disconnect(self, ctx):
        """
        Disconnect from the current voice channel.
        """
        if ctx.message.server.id not in self.musics:
            await self.bot.say(":x: I am not connected to voice.")
            return

        m = self.get_server_music(ctx.message.server)
        await m.disconnect()
        await self.bot.say(":skull_and_crossbones:")

    @commands.command(pass_context=True)
    async def play(self, ctx, *, query: str):
        """
        Plays a track.
        """
        if not ctx.message.author.voice.voice_channel:
            await self.bot.say(":x: You must be in a voice channel.")
            return

        m = self.get_server_music(ctx.message.server)

        if ctx.message.server.me.voice.voice_channel \
                and ctx.message.server.me.voice.voice_channel != ctx.message.author.voice_channel:
            await self.bot.say(":x: I am already playing elsewhere in this server.")
            return

        info = await m.download_information(ctx, query)

        if info is None:
            await self.bot.say(":x: No results found.")
            return

        # Check for a playlist.
        if "entries" in info and len(info['entries']) > 1:
            # Playlist!
            is_playlist = True
            track_data = info['entries']
        else:
            # We might be a single video inside a playlist. Get that out.
            if 'entries' in info:
                track_data = [info['entries'][0]]
            else:
                # Otherwise, we're a single song.
                track_data = [info]
            is_playlist = False

            # Fix for infinite duration livestreams or similar.
            if info.get("is_live"):
                track_data[0]["duration"] = 0

        # Get the voice client.
        m.voice_client = await m.ensure_voice_connected(ctx, ctx.message.author.voice.voice_channel)
        if not m.voice_client:
            return
        # Pass in the data for it to construct the appropriate tuples.
        added = m.construct_voice_data(track_data, is_playlist)
        await self.bot.say(":heavy_check_mark: Added {} track(s) to the queue.".format(added))

        # Create the run() task.
        if not m.player_task:
            t = self.bot.loop.create_task(m.run(ctx))
            m.player_task = t

            try:
                await t
            except asyncio.CancelledError:
                pass


def setup(bot):
    bot.add_cog(Music(bot))
