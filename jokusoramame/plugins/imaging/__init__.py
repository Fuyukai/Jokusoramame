from array import array
from itertools import chain

import asks
import curio
import wave
from PIL import Image
from asks.response_objects import Response
from curious import Member
from curious.commands import Context, Plugin, command
from io import BytesIO
from pysstv.color import Robot36
from pysstv.sstv import SSTV


class Imaging(Plugin):
    """
    Imaging commands.
    """

    @staticmethod
    def write_wav(sstv: SSTV) -> bytes:
        """
        Writes an SSTV file to a wav file.
        """
        fmt = sstv.BITS_TO_STRUCT[sstv.bits]
        data = array(fmt, sstv.gen_samples())
        if sstv.nchannels != 1:
            data = array(fmt, chain.from_iterable(
                zip(*([data] * sstv.nchannels))))

        by = BytesIO()
        # prevent Wave_write from closing the file
        by.close = lambda *args, **kwargs: None
        wav = wave.Wave_write(by)
        wav.setnchannels(sstv.nchannels)
        wav.setsampwidth(sstv.bits // 8)
        wav.setframerate(sstv.samples_per_sec)
        wav.writeframes(data.tobytes())
        wav.close()
        return by.getvalue()

    def _do_sstv(self, image_data: bytes):
        """
        SSTVifies an image.
        """
        image: Image.Image = Image.open(BytesIO(image_data))
        image = image.resize((320, 240))
        sstv = Robot36(image, 44100, 16)
        # hacky!
        return self.write_wav(sstv)

    @command()
    async def sstvify(self, ctx: Context, *, target: Member = None):
        """
        SSTVifies the author's avatar.
        """
        if target is None:
            target = ctx.author

        r: Response = await asks.get(target.user.static_avatar_url)
        async with curio.spawn_thread():
            wav_data = self._do_sstv(r.raw)

        by = BytesIO(wav_data)
        await ctx.channel.messages.upload(by, filename="sstv.wav")
