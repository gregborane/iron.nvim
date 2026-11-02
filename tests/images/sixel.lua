-- Real REPL transport and overlay lifecycle, capturing outer-terminal output.
vim.opt.runtimepath:prepend(vim.fn.getcwd())
vim.opt.termguicolors = true
vim.opt.swapfile = false
vim.env.TMUX = nil
vim.env.TERM = "xterm"
local sent = {}
vim.api.nvim_ui_send = function(s) sent[#sent + 1] = s end
local esc = string.char(27)
local image = require("iron.image")
local buf = vim.api.nvim_create_buf(false, true)
local opts = {}
local frontend = arg[1] or "python"
local commands = {
  python = { "python", "-q" },
  ipython = { "python", "-m", "IPython", "--simple-prompt", "--no-autoindent" },
  jupyter = { "python", "-m", "jupyter_console", "--no-confirm-exit", "--transport=ipc" },
}
local cmd = image.prepare("python", commands[frontend], opts, buf, { protocol = "sixel", max_images = 1 })
assert(opts.env.IRON_IMAGE_PROTOCOL == "sixel")
vim.api.nvim_set_current_buf(buf)
local job = vim.fn.termopen(cmd, opts)
local function text() return table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n") end
assert(vim.wait(20000, function() return text():find(frontend == "python" and ">>>" or "In [1]:", 1, true) end), text())
vim.fn.chansend(job, "import matplotlib.pyplot as plt; plt.plot([1,2,3]); plt.show(); print('DONE')\n")
assert(vim.wait(15000, function() vim.cmd("redraw"); return table.concat(sent):find(esc .. "P0;1;0q", 1, true) end), text())
assert(not text():find(vim.fn.nr2char(0x10eeee), 1, true), "Kitty placeholders in SIXEL buffer")
assert(not table.concat(sent):find(esc .. "_G", 1, true), "Kitty commands in SIXEL mode")
local before = #sent
vim.cmd("redraw!")
assert(vim.wait(1000, function() return #sent > before end), "overlay not repainted")
vim.env.TMUX = "/tmp/test"
before = #sent
vim.cmd("redraw!")
assert(vim.wait(1000, function() return #sent > before end))
assert(sent[#sent]:sub(1, 7) == esc .. "Ptmux;", "missing tmux passthrough")
vim.fn.chansend(job, "exit()\n")
assert(vim.fn.jobwait({job}, 15000)[1] == 0, "REPL did not exit")
image.detach(buf)
vim.wait(50, function() return false end)
before = #sent
vim.cmd("redraw!")
vim.wait(50, function() return false end)
assert(#sent == before, "detached overlay repainted")
vim.api.nvim_buf_delete(buf, { force = true })
for _, settings in ipairs({ { protocol = "unknown" }, { protocol = "sixel", cell_width = 0 } }) do
  local target = vim.api.nvim_create_buf(false, true)
  assert(not pcall(image.prepare, "python", { "python" }, {}, target, settings))
  vim.api.nvim_buf_delete(target, { force = true })
end
-- Exercise clipping, float occlusion and eviction without needing a terminal.
vim.env.TMUX = nil
local target = vim.api.nvim_create_buf(false, true)
vim.api.nvim_set_current_buf(target)
vim.api.nvim_buf_set_lines(target, 0, -1, false, vim.fn["repeat"]({ "    " }, 60))
local renderer = require("iron.sixel")
local first = esc .. 'P0;1;0q"1;1;1;1#0;2;100;0;0@' .. esc .. "\\"
local second = first:gsub("100;0;0", "0;100;0")
renderer.receive(target, first, 2, 3, { 1, 0 }, 1)
vim.cmd("normal! ggzt")
vim.cmd("redraw!")
vim.wait(50, function() return false end)
assert(sent[#sent]:find(first, 1, true))
renderer.receive(target, second, 2, 3, { 1, 0 }, 1)
vim.wait(50, function() return false end)
assert(sent[#sent]:find(second, 1, true), "new image missing after eviction")
sent = {}
vim.cmd("normal! 40Gzt")
vim.cmd("redraw!")
vim.wait(50, function() return false end)
assert(#sent == 0, "offscreen image painted")
vim.cmd("normal! ggzt")
vim.cmd("redraw!")
vim.wait(50, function() return false end)
assert(sent[#sent]:find(second, 1, true), "scrollback image not restored")
local floating = vim.api.nvim_open_win(vim.api.nvim_create_buf(false, true), false,
  { relative = "editor", row = 0, col = 0, width = 10, height = 5 })
sent = {}
vim.cmd("redraw!")
vim.wait(50, function() return false end)
assert(#sent == 0, "image painted over float")
vim.api.nvim_win_close(floating, true)
renderer.detach(target)
vim.api.nvim_buf_delete(target, { force = true })
print("PASS: SIXEL " .. frontend .. ", redraw, tmux, clipping, scrollback, floats, eviction, cleanup, configuration")
