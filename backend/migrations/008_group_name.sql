-- Migration 008 — Commitment groups/sections
--
-- Adds `group_name`: an optional label the commitment belongs to (e.g.
-- "Groceries", "Work", "Overwatch"). Empty string = ungrouped (the default).
-- Lets the list organize commitments into sections, the standard pattern in
-- Todoist/Things/TickTick.
--
-- Named group_name (not "group") because GROUP is a SQL reserved word.
-- Existing rows default to '' (ungrouped), preserving current behavior.

ALTER TABLE commitments ADD COLUMN group_name TEXT NOT NULL DEFAULT '';
