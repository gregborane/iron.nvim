"""Static/interactive routing without opening real browser windows."""
import base64
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
import iron_image


class Routing(unittest.TestCase):
    def test_pillow_show_modes_inline_and_no_external_fallback(self):
        from PIL import Image, ImageShow
        original = list(ImageShow._viewers)
        try:
            iron_image.install_pillow()
            iron_image.install_pillow()
            self.assertEqual(len(ImageShow._viewers), len(original) + 1)
            for mode in ('RGB', 'RGBA', 'CMYK', 'P', 'L'):
                image = Image.new(mode, (3, 2))
                with patch.object(iron_image, 'display') as display:
                    image.show()
                display.assert_called_once()
                with Image.open(io.BytesIO(display.call_args.args[0])) as result:
                    self.assertEqual(result.size, (3, 2))
                    self.assertEqual(result.mode, 'RGBA')
                self.assertEqual(image.mode, mode)
            with patch.object(iron_image, 'display', side_effect=RuntimeError('transport unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'transport unavailable'):
                    image.show()
        finally:
            ImageShow._viewers[:] = original
            iron_image._pillow_viewer = None

    def test_startup_preserves_user_namespace_and_previous_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            startup = Path(directory) / 'startup.py'
            startup.write_text('user_startup_value = 42\n')
            namespace = {'__name__': '__main__'}
            with patch.dict(os.environ, {'IRON_IMAGE_PYTHONSTARTUP': str(startup)}), patch.object(iron_image, 'install_pillow'):
                try:
                    iron_image.run_startup(namespace)
                finally:
                    iron_image._startup_installed = False
            self.assertEqual(namespace['user_startup_value'], 42)
            self.assertFalse(any('iron' in key.lower() for key in namespace))

    def test_kernel_extension_keeps_mime_publisher_and_cleans_up(self):
        from PIL import Image, ImageShow
        from types import SimpleNamespace
        published = []
        shell = type('ZMQInteractiveShell', (), {})()
        shell.display_pub = SimpleNamespace(publish=published.append)
        shell.display_formatter = SimpleNamespace(active_types=['text/plain'])
        original = shell.display_pub.publish
        viewers = list(ImageShow._viewers)
        with patch.dict(sys.modules, {'IPython': SimpleNamespace(get_ipython=lambda: shell)}):
            try:
                iron_image.load_ipython_extension(shell)
                iron_image.load_ipython_extension(shell)
                self.assertIs(shell.display_pub.publish, original)
                output = io.StringIO()
                with redirect_stdout(output):
                    Image.new('CMYK', (2, 2)).show()
                self.assertEqual(output.getvalue(), '')
                self.assertTrue(base64.b64decode(published[0]['image/png']).startswith(b'\x89PNG'))
            finally:
                iron_image.unload_ipython_extension(shell)
        self.assertEqual(ImageShow._viewers, viewers)
        self.assertEqual(shell.display_formatter.active_types, ['text/plain'])

    def test_plotly_default_browser_without_kaleido(self):
        # Fresh interpreter exercises Plotly's environment-driven lazy setup.
        code = '''
from unittest.mock import patch
import plotly.graph_objects as go
import plotly.io as pio
assert pio.renderers.default == "browser"
with patch("plotly.io._base_renderers.open_html_in_browser") as browser:
    go.Figure(go.Scatter(y=[1, 2, 1])).show()
    browser.assert_called_once()
    html = browser.call_args.args[0]
    assert "Plotly.newPlot" in html
    assert "plotly.js" in html
'''
        result = subprocess.run([sys.executable, '-c', code], env={**os.environ, 'PLOTLY_RENDERER': 'browser'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_jupyter_kernel_extension_argument(self):
        from jupyter_console.app import ZMQTerminalIPythonApp
        from ipykernel.kernelapp import IPKernelApp
        console = ZMQTerminalIPythonApp()
        console.parse_command_line(['--', '--IPKernelApp.extensions=iron_image'])
        console.build_kernel_argv()
        kernel = IPKernelApp()
        kernel.parse_command_line(['--IPKernelApp.extensions=user_extension'] + console.kernel_argv)
        self.assertIn('user_extension', kernel.extensions)
        self.assertIn('iron_image', kernel.extensions)
