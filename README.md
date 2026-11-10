# iron.nvim

Interactive Repls Over Neovim.

## What is iron.nvim

[![asciicast](https://asciinema.org/a/495376.svg)](https://asciinema.org/a/495376)
Iron allows you to quickly interact with the repl without having to leave your
work buffer

It both a plugin and a library, allowing for better user experience and
extensibility at the same time.

## How to install

Using [vim.pack](https://neovim.io/doc/user/pack) 
(or the plugin manager of your choice):

```lua
vim.pack.add({
  {
    src = "https://github.com/Vigemus/iron.nvim",
  }
}
```

### REPL config for this fork

Please refer to the original project [iron.nvim](https://github.com/Vigemus/iron.nvim/) for full configuration

```lua
vim.pack.add({
  { src = "https://github.com/gregborane/iron.nvim" },
})

vim.opt.termguicolors = true
local iron = require("iron.core")
local view = require("iron.view")
local common = require("iron.fts.common")

iron.setup({
  config = {
    scratch_repl = true,
    close_window_on_exit = false,
    repl_definition = {
      sh = {
        command = { "sh" },
      },
      python = {
        command = { "jupyter-console" },
        format = common.bracketed_paste,
        image = {
          protocol = "sixel",
          cell_width = 8,
          cell_height = 16,
        },
        block_dividers = { "# %%", "#%%" },
        env = { PYTHON_BASIC_REPL = "1" },
      },
    },
    repl_filetype = function(bufnr, ft)
      return ft
    end,
    dap_integration = true,
    repl_open_cmd = view.split.vertical.rightbelow("%40"),
  },
  highlight = {
    italic = true,
  },
})

vim.keymap.set("n", "<space>rf", "<cmd>IronFocus<cr>")
vim.keymap.set("n", "<space>rr", "<cmd>IronRestart<cr>")
vim.keymap.set("n", "<space>ro", "<cmd>IronRepl<cr>")
vim.keymap.set("n", "<space>rh", "<cmd>IronHide<cr>")
vim.keymap.set("n", "<space>rq", "<cmd>IronQuit<cr>")
vim.keymap.set("n", "<space>rc", "<cmd>IronClear<cr>")
vim.keymap.set("n", "<space>x", "<cmd>IronExecCell<cr>")
vim.keymap.set("n", "<space>rx", "<cmd>IronInterupt<cr>")
```


### REPL windows

iron.nvim supports both splits and floating windows and has helper functions
for opening new repls in either of them:

#### For splits

If you prefer using splits to your repls, iron provides a few utility functions
to make it simpler:

```lua
local view = require("iron.view")
repl_open_cmd = view.split("40%")
})
```

#### For floats

If you prefer floats, the API is the following:

```lua
local view = require("iron.view")

repl_open_cmd = view.offset{
  width = 60,
  height = vim.o.height * 0.75
  w_offset = 0,
  h_offset = "5%"
}
```

