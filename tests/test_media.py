from io import BytesIO

from PIL import Image, ImageSequence

from group_watch.utils.images import _animation
from group_watch.utils.images import webp


def test_duplicate_animation_frames_keep_timing_and_alpha():
    first = Image.new('RGBA', (12, 10), (220, 30, 20, 0))
    first.putpixel((4, 5), (220, 30, 20, 128))
    last = Image.new('RGBA', first.size, (20, 30, 220, 255))
    durations = [40, 120, 70]
    raw = _animation([first, first.copy(), last], durations, 3)

    result = webp(raw)

    with Image.open(BytesIO(raw)) as original, Image.open(BytesIO(result)) as output:
        assert output.size == original.size
        assert output.n_frames == original.n_frames == 3
        assert output.info['loop'] == 3
        actual = []
        for before, after in zip(ImageSequence.Iterator(original), ImageSequence.Iterator(output)):
            before.load()
            after.load()
            actual.append(after.info['duration'])
            assert after.convert('RGBA').getchannel('A').tobytes() == before.convert('RGBA').getchannel('A').tobytes()
        assert actual == durations


def test_gif_animation_keeps_canvas_durations_and_loop():
    frames = [Image.new('RGB', (13, 11), color) for color in ('red', 'blue', 'green')]
    source = BytesIO()
    frames[0].save(source, format='GIF', save_all=True, append_images=frames[1:],
                   duration=[30, 80, 150], loop=2)
    with Image.open(BytesIO(webp(source.getvalue()))) as output:
        assert output.size == (13, 11)
        assert output.n_frames == 3
        assert output.info['loop'] == 2
        durations = []
        for frame in ImageSequence.Iterator(output):
            frame.load()
            durations.append(frame.info['duration'])
        assert durations == [30, 80, 150]
