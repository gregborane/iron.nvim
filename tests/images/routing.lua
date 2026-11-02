-- Start real image-enabled REPLs. Stub only browser launch, never rendering.
vim.opt.runtimepath:prepend(vim.fn.getcwd())
vim.opt.termguicolors = true
vim.opt.swapfile = false
local image = require("iron.image")
local sent = {}
vim.api.nvim_ui_send = function(s) sent[#sent + 1] = s end
local function run(command, ipython)
  sent = {}
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_set_current_buf(buf)
  local startup = vim.fn.tempname()
  vim.fn.writefile({ "startup_kept = 42" }, startup)
  local opts = { env = { PYTHONSTARTUP = startup } }
  command = image.prepare("python", command, opts, buf, { protocol = "kitty" })
  assert(opts.env.PLOTLY_RENDERER == "browser")
  local job = vim.fn.termopen(command, opts)
  local function text() return table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n") end
  local function wait_for(test)
    assert(vim.wait(15000, test, 10), text())
  end
  wait_for(function() return text():find(ipython and "In [1]:" or ">>>", 1, true) end)
  if not ipython then
    vim.fn.chansend(job, "print('STARTUP', startup_kept, any('iron' in k.lower() for k in globals()))\n")
    wait_for(function() return text():find("STARTUP 42 False", 1, true) end)
  end
  vim.fn.chansend(job, "from PIL import Image; img = Image.new('CMYK', (120, 60), (0,255,255,0)); img.show()\n")
  wait_for(function() return table.concat(sent):find("a=p,U=1", 1, true) end)
  if ipython then
    local count = #sent
    vim.fn.chansend(job, "display(img.convert('RGB'))\n")
    wait_for(function() return #sent > count end)
    count = #sent
    vim.fn.chansend(job, "img.convert('RGB')\n")
    wait_for(function() return #sent > count end)
  end
  vim.fn.chansend(job, "import plotly.graph_objects as go; import plotly.io._base_renderers as br; br.open_html_in_browser = lambda html, *args, **kw: print('BROWSER', 'Plotly.newPlot' in html); pfig = go.Figure(go.Scatter(y=[1,3,2])); pfig.show()\n")
  wait_for(function() return text():find("BROWSER True", 1, true) end)
  if ipython then
    -- Bare expressions use Plotly's IPython display hook as well.
    local before = select(2, text():gsub("BROWSER True", ""))
    vim.fn.chansend(job, "pfig\n")
    wait_for(function() return select(2, text():gsub("BROWSER True", "")) > before end)
  end
  vim.fn.chansend(job, "exit()\n")
  assert(vim.fn.jobwait({job}, 15000)[1] == 0, text())
  vim.api.nvim_buf_delete(buf, { force = true })
  vim.fn.delete(startup)
end
run({ "python", "-q" }, false)
run({ "python", "-m", "IPython", "--simple-prompt", "--no-autoindent" }, true)
print("PASS: automatic Pillow inline output, Plotly browser routing, bare Plotly figures, startup preservation")
