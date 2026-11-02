"""Real TUI regression test. Requires POSIX, Neovim and the test-only pyte package.

Run: NVIM=/path/to/nvim python -m unittest discover -s tests/images -p test_tui_redraw.py
Unlike a headless API mock, this decodes the bytes sent to the host terminal.
SIXEL payloads are excluded: this tests text preservation, not bitmap rendering.
"""
import importlib.util
import os
from pathlib import Path
import re
import select
import shutil
import struct
import subprocess
import tempfile
import time
import unittest

NVIM = os.environ.get('NVIM') or shutil.which('nvim')
ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == 'posix' and NVIM and importlib.util.find_spec('pyte'),
                     'requires POSIX, Neovim and pyte')
class TuiRedraw(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = subprocess.run(
            [NVIM, '--headless', '-u', 'NONE', '-i', 'NONE', '-c',
             'lua io.write(type(vim.api.nvim_ui_send))', '-c', 'qa!'],
            capture_output=True, text=True, timeout=10, check=True)
        if probe.stdout != 'function':
            raise unittest.SkipTest('SIXEL requires Neovim 0.12+ with nvim_ui_send')

    def test_text_survives_image_redraw_and_detach(self):
        import fcntl
        import pty
        import termios
        import pyte

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            script = directory / 'fixture.lua'
            ready = directory / 'ready'
            advance = directory / 'advance'
            # Environment paths avoid quoting filenames into Lua code.
            script.write_text('''
vim.opt.runtimepath:prepend(vim.fn.getcwd())
vim.opt.termguicolors = true
vim.opt.swapfile = false
vim.opt.laststatus = 0
vim.opt.ruler = false
vim.api.nvim_buf_set_lines(0, 0, -1, false, {
  'REPL_TEXT_MUST_SURVIVE', '', '', '', '', '', '', '', 'PROMPT_MUST_SURVIVE'
})
local buf = vim.api.nvim_get_current_buf()
vim.cmd('leftabove vnew')
vim.api.nvim_buf_set_lines(0, 0, -1, false, {'EDITOR_TEXT_MUST_SURVIVE'})
vim.cmd('wincmd p')
local renderer = require('iron.sixel')
vim.defer_fn(function()
  renderer.receive(buf, '\\027P0;1;0q"1;1;1;1#0;2;100;0;0@\\027\\\\', 2, 3, {3, 0}, 10)
end, 100)
vim.defer_fn(function() vim.cmd('redraw!') end, 300)
vim.defer_fn(function() vim.fn.writefile({'painted'}, vim.env.IRON_TUI_READY) end, 600)
local function check()
  if vim.fn.filereadable(vim.env.IRON_TUI_ADVANCE) == 1 then
    renderer.detach(buf)
    vim.defer_fn(function() vim.fn.writefile({'detached'}, vim.env.IRON_TUI_READY) end, 100)
  else
    vim.defer_fn(check, 50)
  end
end
vim.defer_fn(check, 650)
''')
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
            env = {**os.environ, 'TERM': 'xterm-256color',
                   'IRON_TUI_READY': str(ready), 'IRON_TUI_ADVANCE': str(advance),
                   'IRON_TUI_SCRIPT': str(script)}
            env.pop('TMUX', None)
            proc = subprocess.Popen(
                [NVIM, '-u', 'NONE', '-i', 'NONE', '-n', '-c',
                 'lua dofile(vim.env.IRON_TUI_SCRIPT)'],
                cwd=ROOT, stdin=slave, stdout=slave, stderr=slave, env=env)
            os.close(slave)
            output = b''
            try:
                for stage in ('painted', 'detached'):
                    deadline = time.monotonic() + 8
                    settled = None
                    while time.monotonic() < deadline:
                        if select.select([master], [], [], 0.03)[0]:
                            output += os.read(master, 65536)
                        if ready.exists() and ready.read_text().strip() == stage and settled is None:
                            settled = time.monotonic()
                        if settled and time.monotonic() - settled > 0.2:
                            break
                    self.assertIsNotNone(settled, output[-1000:])
                    self.assertIn(b'\x1bP0;1;0q', output, 'No SIXEL emitted')
                    text = re.sub(rb'\x1bP.*?\x1b\\', b'', output, flags=re.S)
                    text = re.sub(rb'\x1b\].*?(?:\x07|\x1b\\)', b'', text, flags=re.S)
                    # pyte does not implement the graphics-specific private modes.
                    text = re.sub(rb'\x1b\[\?(?:80|1070)[srhl]', b'', text)
                    screen = pyte.Screen(80, 24)
                    pyte.ByteStream(screen).feed(text)
                    view = '\n'.join(screen.display)
                    self.assertIn('REPL_TEXT_MUST_SURVIVE', view, stage)
                    self.assertIn('PROMPT_MUST_SURVIVE', view, stage)
                    self.assertIn('EDITOR_TEXT_MUST_SURVIVE', view, stage)
                    # A host-terminal clear must accompany the repaint, to
                    # remove stale graphics as well as restoring unchanged text.
                    self.assertIn(b'\x1b[2J', output)
                    last_image = output.rfind(b'\x1bP0;1;0q')
                    last_clear = output.rfind(b'\x1b[2J')
                    if stage == 'painted':
                        self.assertGreater(last_image, last_clear, 'TUI erased the freshly painted image')
                    else:
                        self.assertGreater(last_clear, last_image, 'detached image was not cleared')
                    advance.touch()
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                os.close(master)
