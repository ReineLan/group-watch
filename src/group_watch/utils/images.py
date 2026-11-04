"""Canonical archive images: q80 WebP, original canvas, alpha and animation."""
from io import BytesIO
from PIL import Image, ImageSequence


def _chunk(kind, payload):
    return kind + len(payload).to_bytes(4, 'little') + payload + b'\0' * (len(payload) % 2)


def _animation(frames, durations, loop):
    # Encode frames separately so libwebp cannot merge identical adjacent frames.
    # https://developers.google.com/speed/webp/docs/riff_container
    width, height = frames[0].size
    u24 = lambda value: int(value).to_bytes(3, 'little')
    alpha = any('A' in frame.getbands() and frame.getchannel('A').getextrema()[0] < 255 for frame in frames)
    chunks = [_chunk(b'VP8X', bytes([2 | (16 if alpha else 0)]) + b'\0' * 3 + u24(width-1) + u24(height-1)),
              _chunk(b'ANIM', b'\0' * 4 + int(loop).to_bytes(2, 'little'))]
    for frame, duration in zip(frames, durations):
        output = BytesIO()
        frame.save(output, format='WEBP', quality=80, method=6, exact=True)
        data, position, parts = output.getvalue(), 12, []
        while position < len(data):
            size = int.from_bytes(data[position+4:position+8], 'little')
            end = position + 8 + size + size % 2
            if data[position:position+4] in (b'ALPH', b'VP8 ', b'VP8L'):
                parts.append(data[position:end])
            position = end
        # Full composited frames overwrite the canvas, including transparent pixels.
        header = b'\0' * 6 + u24(width-1) + u24(height-1) + u24(duration) + b'\x02'
        chunks.append(_chunk(b'ANMF', header + b''.join(parts)))
    payload = b'WEBP' + b''.join(chunks)
    return b'RIFF' + len(payload).to_bytes(4, 'little') + payload


def webp(raw):
    with Image.open(BytesIO(raw)) as image:
        loop = image.info.get('loop', 0)
        frames, durations = [], []
        for frame in ImageSequence.Iterator(image):
            frame.load()
            frames.append(frame.convert('RGBA' if 'A' in frame.getbands() or 'transparency' in frame.info else 'RGB'))
            durations.append(frame.info.get('duration', 100))
        if not frames:
            raise ValueError('图片不包含有效帧')
        output = BytesIO()
        options = dict(format='WEBP', quality=80, method=6, exact=True)
        if len(frames)>1:
            options.update(save_all=True,append_images=frames[1:],duration=durations,loop=loop)
        frames[0].save(output,**options)
        result=output.getvalue()
        if len(frames)>1:
            with Image.open(BytesIO(result)) as check:
                if check.n_frames!=len(frames):
                    result=_animation(frames,durations,loop)
        with Image.open(BytesIO(result)) as check:
            if check.size!=image.size or check.n_frames!=len(frames):
                raise ValueError('图片转换未保留画布或帧')
            if len(frames)>1:
                actual=[]
                for frame in ImageSequence.Iterator(check):
                    frame.load()
                    actual.append(frame.info.get('duration',100))
                if actual!=durations or check.info.get('loop',0)!=loop:
                    raise ValueError('图片转换未保留动画时序')
        return result
