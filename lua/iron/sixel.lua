-- SIXEL has no image IDs or text placeholders. Keep buffer anchors and repaint
-- visible images after the TUI redraws. Never write SIXEL to the embedded PTY.
if type(vim.api.nvim_ui_send) ~= "function" then
  error("iron: SIXEL requires Neovim 0.12+ (nvim_ui_send) for ordered terminal redraws")
end
local M = {}
local ns = vim.api.nvim_create_namespace("IronSixel")
local images = {}
local esc = string.char(27)
local queued, painting = false, false
local painted = false

local function send(sequence)
  if (vim.env.TMUX and vim.env.TMUX ~= "") or (vim.env.TERM or ""):match("^tmux") then
    sequence = esc .. "Ptmux;" .. sequence:gsub(esc, esc .. esc) .. esc .. "\\"
  end
  -- Queue graphics on the same UI stream as the preceding clear/repaint.
  -- Direct stderr writes can overtake the TUI and be erased by its redraw.
  vim.api.nvim_ui_send(sequence)
end

local function reserved(buf, line, item)
  if item.invalid then return false end
  local lines = vim.api.nvim_buf_get_lines(buf, line, line + item.rows, false)
  if #lines ~= item.rows then
    if item.reserved then item.invalid = true end
    return false
  end
  for _, text in ipairs(lines) do
    -- Terminal updates may replace a marked line in place. An extmark alone
    -- does not prove that the image's reservation still belongs to the image.
    if text:find("%S") then
      if item.reserved then item.invalid = true end
      return false
    end
  end
  item.reserved = true
  return true
end

local function placements()
  local result = {}
  -- Floating windows and popup menus can cover a normal window. Hide overlays
  -- while they are present rather than painting through their contents.
  if vim.fn.pumvisible() == 1 then return result end
  local wins = vim.api.nvim_tabpage_list_wins(0)
  for _, win in ipairs(wins) do
    if vim.api.nvim_win_get_config(win).relative ~= "" then return result end
  end
  for _, win in ipairs(wins) do
    local buf = vim.api.nvim_win_get_buf(win)
    for _, item in ipairs(images[buf] or {}) do
      local mark = vim.api.nvim_buf_get_extmark_by_id(buf, ns, item.mark, { details = true })
      if #mark > 0 and not mark[3].invalid and reserved(buf, mark[1], item) then
        local first = vim.fn.screenpos(win, mark[1] + 1, 1)
        local last = vim.fn.screenpos(win, mark[1] + item.rows, 1)
        local info = vim.fn.getwininfo(win)[1]
        -- Only whole, unwrapped rectangles are painted. A clipped image must
        -- never overflow into another split, a statusline, or the command line.
        if first.row > 0 and last.row == first.row + item.rows - 1
          and first.col + item.cols <= info.wincol + info.width
          and last.row < info.winrow + info.height then
          result[#result + 1] = { row = first.row, col = first.col, item = item }
        end
      end
    end
  end
  return result
end

local function paint()
  local visible = placements()
  if painted or #visible > 0 then
    -- :redraw! only invalidates the editor's grid. It does not invalidate the
    -- TUI's cached cells, so raw ECH erasure leaves unchanged text invisible.
    -- :mode requests UPD_CLEAR: Neovim clears its terminal and repaints its
    -- complete grid, keeping the physical screen and both caches consistent.
    -- Do not erase terminal text ourselves. Hold the guard during the repaint.
    vim.cmd("mode")
    visible = placements()
  end
  painted = #visible > 0
  for _, p in ipairs(visible) do
    send(esc .. "7" .. esc .. "[?80s" .. esc .. "[?80l"
      .. esc .. "[?1070s" .. esc .. "[?1070h"
      .. (esc .. "[%d;%dH"):format(p.row, p.col) .. p.item.data
      .. esc .. "[?1070r" .. esc .. "[?80r" .. esc .. "8")
  end
end

local function schedule()
  if queued or painting then return end
  queued = true
  vim.schedule(function()
    painting = true
    local ok, err = pcall(paint)
    painting = false
    queued = false
    if not ok then vim.notify("iron: SIXEL redraw failed: " .. tostring(err), vim.log.levels.WARN) end
  end)
end

vim.api.nvim_set_decoration_provider(ns, {
  on_end = function() if next(images) or painted then schedule() end end,
})

function M.receive(buf, data, cols, rows, cursor, limit)
  if not cursor or cursor[1] < 1 or cursor[1] > vim.api.nvim_buf_line_count(buf) then return false end
  local mark = vim.api.nvim_buf_set_extmark(buf, ns, cursor[1] - 1, 0, {
    right_gravity = false, invalidate = true, undo_restore = false,
  })
  local list = images[buf] or {}
  images[buf] = list
  list[#list + 1] = { mark = mark, data = data, cols = cols, rows = rows }
  if #list > limit then
    vim.api.nvim_buf_del_extmark(buf, ns, table.remove(list, 1).mark)
  end
  schedule()
  return true
end

function M.detach(buf)
  images[buf] = nil
  if vim.api.nvim_buf_is_valid(buf) then vim.api.nvim_buf_clear_namespace(buf, ns, 0, -1) end
  schedule()
end

return M
