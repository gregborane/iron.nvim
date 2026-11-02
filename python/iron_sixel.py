"""Bounded SIXEL encoder. Pillow is imported only when SIXEL is selected."""
import io
import re


_SIXEL_CHARS = bytes.maketrans(bytes(range(64)), bytes(range(63, 127)))
_RUNS = re.compile(r"(.)\1{3,}")


def _repeat(match):
    return f"!{len(match[0])}{match[1]}"


def encode(png, width, height):
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("iron: SIXEL requires Pillow (python -m pip install Pillow)") from error

    with Image.open(io.BytesIO(png)) as source:
        # Avoid allocating huge decompressed images from a small PNG.
        if source.width * source.height > 16_000_000:
            raise ValueError("iron: SIXEL source exceeds 16 million pixels")
        source.thumbnail((width, height))
        rgba = source.convert("RGBA")
    background = Image.new("RGBA", rgba.size, "white")
    background.alpha_composite(rgba)
    image = background.convert("RGB").quantize(colors=256)
    width, height = image.size
    palette = image.getpalette()
    pixels = image.tobytes()
    output = [f'\x1bP0;1;0q"1;1;{width};{height}']
    for color in sorted(set(pixels)):
        rgb = palette[color * 3:color * 3 + 3]
        output.append(f'#{color};2;' + ';'.join(str(round(v * 100 / 255)) for v in rgb))
    for top in range(0, height, 6):
        # Palette indices are bytes: direct indexing avoids a dictionary lookup
        # and membership test for every pixel. Allocate only colors in this band.
        bands = [None] * 256
        used = []
        for y in range(top, min(top + 6, height)):
            bit = 1 << (y - top)
            offset = y * width
            for x, color in enumerate(pixels[offset:offset + width]):
                band = bands[color]
                if band is None:
                    band = bands[color] = bytearray(width)
                    used.append(color)
                band[x] |= bit
        for color in sorted(used):
            output.append(f'#{color}')
            # Translate and scan runs in C, avoiding Python work for each zero
            # column (especially costly with many sparse color planes).
            chars = bands[color].rstrip(b'\0').translate(_SIXEL_CHARS).decode('ascii')
            output.append(_RUNS.sub(_repeat, chars))
            output.append('$')
        if top + 6 < height:
            output.append('-')
    output.append('\x1b\\')
    return ''.join(output).encode('ascii')
