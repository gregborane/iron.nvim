-- SIXEL has no image IDs or text placeholders. Keep buffer anchors and repaint
-- visible images after the TUI redraws. Never write SIXEL to the embedded PTY.
local M = {}
local ns = vim.api.nvim_create_namespace("IronSixel")
local images = {}
local esc = string.char(27)
local queued, painting = false, false
local previous_areas = {}

local function send(sequence)
  if (vim.env.TMUX and vim.env.TMUX ~= "") or (vim.env.TERM or ""):match("^tmux") then
    sequence = esc .. "Ptmux;" .. sequence:gsub(esc, esc .. esc) .. esc .. "\\"
  end
  if type(vim.api.nvim_ui_send) == "function" then
    vim.api.nvim_ui_send(sequence)
  else
    vim.api.nvim_chan_send(vim.v.stderr, sequence)
  end
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
          result[#result + 1] = { row = first.row, col = first.col, item = item, area = {
            winrow = info.winrow, wincol = info.wincol, width = info.width, height = info.height,
          } }
        end
      end
    end
  end
  return result
end

local function erase(areas)
  local seen, commands = {}, { esc .. "7", esc .. "[0m" }
  for _, area in ipairs(areas) do
    local key = ("%d:%d:%d:%d"):format(area.winrow, area.wincol, area.width, area.height)
    if not seen[key] then
      seen[key] = true
      -- Clear the whole image-bearing window: terminal hardware scrolling may
      -- have moved old pixels away from their last recorded image rectangle.
      for row = area.winrow, math.min(vim.o.lines, area.winrow + area.height - 1) do
        local width = math.min(area.width, vim.o.columns - area.wincol + 1)
        if width > 0 then
          commands[#commands + 1] = (esc .. "[%d;%dH" .. esc .. "[%dX"):format(row, area.wincol, width)
        end
      end
    end
  end
  commands[#commands + 1] = esc .. "8"
  send(table.concat(commands))
end

local function paint()
  local visible = placements()
  local areas = {}
  for _, p in ipairs(visible) do areas[#areas + 1] = p.area end
  if #previous_areas > 0 or #areas > 0 then
    local clear = vim.list_extend(vim.deepcopy(previous_areas), areas)
    erase(clear)
    -- Explicit erasure damages text too, so restore the entire TUI before
    -- painting images. Keep the reentrancy guard through the whole operation.
    vim.cmd("redraw!")
    visible = placements()
  end
  previous_areas = {}
  for _, p in ipairs(visible) do
    previous_areas[#previous_areas + 1] = p.area
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
  on_end = function() if next(images) or #previous_areas > 0 then schedule() end end,
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
