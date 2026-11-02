"""Inline PNGs for Iron's Python REPL. Kitty transport needs only the stdlib.

Like pyrepl.nvim, images use Kitty virtual placements and Unicode placeholders.
Iron forwards bounded OSC messages through Neovim's TermRequest event, avoiding
an RPC client, temporary image files, or a Kitty executable. SIXEL mode uses
Pillow to encode images and reserves blank lines for Neovim-managed overlays.
"""

import base64
import itertools
import io
import os
import shutil
import sys
import threading

PLACEHOLDER = "\U0010eeee"
# First 20 entries of Kitty's row/column diacritics table.
DIACRITICS = (
    "\u0305\u030d\u030e\u0310\u0312\u033d\u033e\u033f\u0346\u034a"
    "\u034b\u034c\u0350\u0351\u0352\u0357\u035b\u0363\u0364\u0365"
)
_ids = itertools.count(1)
_lock = threading.RLock()
_extensions = {}
_pillow_viewer = None
_startup_installed = False
MAX_PNG_BYTES = 12 * 1024 * 1024


def display(image):
    """Display a PNG path, PNG bytes, or an object implementing _repr_png_."""
    if isinstance(image, (str, os.PathLike)):
        with open(image, "rb") as source:
            png = source.read(MAX_PNG_BYTES + 1)
    elif isinstance(image, (bytes, bytearray)):
        png = bytes(image)
    elif hasattr(image, "_repr_png_"):
        png = image._repr_png_()
        if isinstance(png, tuple):
            png = png[0]
        if isinstance(png, str):
            png = base64.b64decode(png, validate=True)
    else:
        raise TypeError("iron: display expects PNG bytes, a PNG path, or _repr_png_")
    if not isinstance(png, bytes):
        raise ValueError("iron: object did not provide PNG data")
    if len(png) > MAX_PNG_BYTES:
        raise ValueError("iron: PNG exceeds the 12 MiB image limit")
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        raise ValueError("iron: expected PNG data")
    if not int.from_bytes(png[16:20], "big") or not int.from_bytes(png[20:24], "big"):
        raise ValueError("iron: PNG dimensions must be positive")
    # A Jupyter kernel's stdout is a message stream, not the frontend terminal.
    # Publish MIME data so the frontend allocates IDs and sizes the placement.
    shell = getattr(sys.modules.get("IPython"), "get_ipython", lambda: None)()
    if shell is not None and shell.__class__.__name__ == "ZMQInteractiveShell":
        shell.display_pub.publish({"image/png": base64.b64encode(png).decode("ascii")})
        return
    namespace = int(os.environ.get("IRON_IMAGE_NAMESPACE", "0"))
    if not 128 <= namespace <= 255:
        raise RuntimeError("iron: enable image = true in the Python REPL definition")
    terminal = shutil.get_terminal_size((80, 24))
    # Use the reference IPython renderer's fixed bounding box.
    cols = max(1, min(terminal.columns - 3, 80))
    rows = max(1, min(terminal.lines // 2, 20))
    protocol = os.environ.get("IRON_IMAGE_PROTOCOL", "kitty")
    if protocol not in ("kitty", "sixel"):
        raise ValueError("iron: unknown image protocol")
    data = png
    if protocol == "sixel":
        from iron_sixel import encode
        cell_width = int(os.environ.get("IRON_IMAGE_CELL_WIDTH", "8"))
        cell_height = int(os.environ.get("IRON_IMAGE_CELL_HEIGHT", "16"))
        data = encode(png, cols * cell_width, rows * cell_height)
        if len(data) > MAX_PNG_BYTES:
            raise ValueError("iron: SIXEL exceeds the 12 MiB image limit")
    payload = base64.b64encode(data).decode("ascii")
    with _lock:
        serial = next(_ids)
        if serial >= 65536:
            raise RuntimeError("iron: image ID space exhausted; restart the REPL")
        image_id = namespace * 65536 + serial
        out = sys.stdout
        # PNG upload and placement are forwarded by Neovim to the outer terminal.
        for part, offset in enumerate(range(0, len(payload), 4096)):
            chunk = payload[offset:offset + 4096]
            more = int(offset + len(chunk) < len(payload))
            out.write(f"\x1b]51;iron-image;{image_id};{cols};{rows};{part};{more};{chunk}\x07")
        if protocol == "sixel":
            # Reserve real terminal lines; Neovim anchors the overlay at the OSC.
            out.write(("\r" + " " * cols + "\r\n") * rows)
            out.flush()
            return
        color = f"\x1b[38;2;{image_id >> 16};{(image_id >> 8) & 255};{image_id & 255}m"
        padding = " " * max(0, (terminal.columns - cols) // 2)
        for row in range(rows):
            # Explicit row AND column-zero markers make redraw/clipping unambiguous.
            cells = PLACEHOLDER + DIACRITICS[row] + DIACRITICS[0] + PLACEHOLDER * (cols - 1)
            out.write("\r" + padding + color + cells + "\x1b[39m\r\n")
        out.flush()


def display_jupyter(data):
    """Jupyter-console callable image handler; False preserves text fallback."""
    png = data.get("image/png")
    if png is None:
        return False
    try:
        if isinstance(png, str):
            if len(png) > 4 * ((MAX_PNG_BYTES + 2) // 3):
                raise ValueError("iron: PNG exceeds the 12 MiB image limit")
            png = base64.b64decode(png, validate=True)
        display(png)
    except (ValueError, TypeError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        return False
    return True


def install_pillow():
    """Prefer inline output for Image.show(), without requiring Pillow."""
    global _pillow_viewer
    if _pillow_viewer is not None:
        return
    try:
        from PIL import ImageShow
    except ModuleNotFoundError as error:
        if error.name == "PIL":
            return
        raise

    class InlineViewer(ImageShow.Viewer):
        def show(self, image, **options):
            output = io.BytesIO()
            # PNG cannot represent modes such as CMYK. Preserve alpha and do
            # not modify the caller's image or fall back to an external viewer.
            image.convert("RGBA").save(output, format="PNG")
            display(output.getvalue())
            return True

    _pillow_viewer = InlineViewer()
    ImageShow.register(_pillow_viewer, order=0)


def configure_browser():
    """Select Plotly's default-browser renderer without importing Plotly."""
    renderer = os.environ.setdefault("PLOTLY_RENDERER", "browser")
    loaded = sys.modules.get("plotly.io")
    if loaded is not None:
        loaded.renderers.default = renderer


def run_startup(namespace):
    """Install hooks, then execute the user's original Python startup file."""
    global _startup_installed
    install_pillow()
    configure_browser()
    _startup_installed = True
    startup = os.environ.get("IRON_IMAGE_PYTHONSTARTUP")
    if startup:
        try:
            with open(startup, "rb") as source:
                code = compile(source.read(), startup, "exec")
            exec(code, namespace)
        except Exception:
            # Match Python's normal startup behavior: report errors, keep REPL.
            import traceback
            traceback.print_exc()


def load_ipython_extension(shell):
    """Render IPython PNG display data while preserving its normal text output."""
    if id(shell) in _extensions:
        return
    install_pillow()
    configure_browser()
    original = shell.display_pub.publish
    active_types = list(shell.display_formatter.active_types)
    shell.display_formatter.active_types = list(dict.fromkeys(active_types + ["image/png"]))

    def publish(data, metadata=None, **kwargs):
        if "image/png" in data:
            try:
                png = data["image/png"]
                display(base64.b64decode(png, validate=True) if isinstance(png, str) else png)
                return
            except (ValueError, TypeError, RuntimeError) as error:
                print(str(error), file=sys.stderr)
        return original(data, metadata=metadata, **kwargs)

    # Kernels must keep publishing MIME messages to their frontend. Wrapping
    # their publisher would recurse through display() back into publish().
    original_hook = None
    if shell.__class__.__name__ != "ZMQInteractiveShell":
        shell.display_pub.publish = publish
        original_hook = shell.displayhook.write_format_data

        def write_format_data(data, md_dict=None):
            if not display_jupyter(data):
                return original_hook(data, md_dict)

        shell.displayhook.write_format_data = write_format_data
    _extensions[id(shell)] = (original, active_types, original_hook)


def unload_ipython_extension(shell):
    global _pillow_viewer
    previous = _extensions.pop(id(shell), None)
    if previous:
        shell.display_pub.publish, shell.display_formatter.active_types = previous[:2]
        if previous[2] is not None:
            shell.displayhook.write_format_data = previous[2]
    if not _extensions and not _startup_installed and _pillow_viewer is not None:
        from PIL import ImageShow
        if _pillow_viewer in ImageShow._viewers:
            ImageShow._viewers.remove(_pillow_viewer)
        _pillow_viewer = None
