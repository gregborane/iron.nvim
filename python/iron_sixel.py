"""Bounded SIXEL encoder. Pillow is imported only when SIXEL is selected."""
import io
import itertools


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
        bands = {}
        for y in range(top, min(top + 6, height)):
            for x in range(width):
                color = pixels[y * width + x]
                if color not in bands:
                    bands[color] = bytearray(width)
                bands[color][x] |= 1 << (y - top)
        for color, band in sorted(bands.items()):
            output.append(f'#{color}')
            for value, group in itertools.groupby(bytes(band).rstrip(b'\0')):
                count = sum(1 for _ in group)
                char = chr(63 + value)
                output.append(f'!{count}{char}' if count > 3 else char * count)
            output.append('$')
        if top + 6 < height:
            output.append('-')
    output.append('\x1b\\')
    return ''.join(output).encode('ascii')
