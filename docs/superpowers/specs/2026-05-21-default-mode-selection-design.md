# Default Mode Selection — Global + Per-Org

**Date:** 2026-05-21
**Status:** Draft, pending review

## Goal

Let admins choose which bundled mode (`general`, `lead_gen`, `kyc_edd`, `competitive_intel`) is preselected when a user starts a new search. Two tiers: a system-wide default (set by superadmin) and a per-org override (set by org admin). Users can still pick a different mode per search; this only changes the initial selection.

## Non-goals

- Per-user default. (Two-tier only — agreed during brainstorm.)
- Editing mode YAML content.
- Authoring custom modes from the UI.
- Restricting which modes a user can pick. The picker still shows all 4 modes; only the preselection changes.

## Resolution order

`org_settings.default_mode_id` → `core_settings.default_mode_id` → hardcoded `'general'`.

The hardcoded fallback already exists in `app/modes/loader.py:_DEFAULT_MODE_ID`. If a stored value points at an unknown mode id, `get_mode()` falls back to `general` with a warning — no special handling needed.

## Storage

### Global default
Reuse the existing `core_settings` table. New key:

- **Key:** `default_mode_id`
- **Value:** one of `general | lead_gen | kyc_edd | competitive_intel`
- **Editor:** superadmin via the existing Settings → Core Settings UI.

No schema change for the global tier.

### Per-org default
New table `org_settings`, modeled on `core_settings`:

```sql
CREATE TABLE IF NOT EXISTS org_settings (
  org_id     UUID NOT NULL,
  key        TEXT NOT NULL,
  value      TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, key)
);
```

First key used: `default_mode_id`. The table is intentionally general so future per-org settings (theme, retention, default search limits) drop in without new tables.

Migration runs in the same bootstrap path as `core_settings` (`app/routers/v3/db.py`).

## Backend

### `app/modes/loader.py`

Add:

```python
def get_default_mode_id(org_id: str | None) -> str:
    """Resolve default mode for an org. org → global → 'general'."""
```

Single source of truth used by both the API and any server-side default selection logic. Reads `org_settings` then `core_settings`, validates the result against `list_modes()` ids, falls back to `_DEFAULT_MODE_ID` on miss or invalid value.

### Endpoints

All under existing `/v3` prefix.

**`GET /v3/modes`**
Returns the bundled mode list for dropdowns and pickers:
```json
[{"id": "general", "label": "General", "description": "..."}, ...]
```
Replaces frontend hardcoding of the mode list. Read-only, any authenticated user.

**`GET /v3/settings/default_mode`**
Returns the resolved default plus its provenance, scoped to the calling user's org:
```json
{
  "resolved": "lead_gen",
  "source": "org",          // "org" | "global" | "fallback"
  "org_value": "lead_gen",  // null if no org override
  "global_value": "general" // null if not set
}
```
Used by Preflight on mount and by Settings to show current state.

**`PUT /v3/settings/default_mode`**
Body:
```json
{"value": "lead_gen" | null, "scope": "global" | "org"}
```
- `value: null` clears the override at the given scope.
- `scope: "global"` requires `is_superadmin`. Writes to `core_settings`.
- `scope: "org"` requires `is_admin` of the calling user's org. Writes to `org_settings` for that org.
- Validates `value` against `list_modes()` ids; rejects unknown ids with 400.

## Frontend

### `frontend/src/pages/Settings.tsx`

New section **"Default mode"** beneath the existing account section.

- **System default** (only visible to superadmin) — single `<select>` populated from `GET /v3/modes`. Saves on change to `PUT /v3/settings/default_mode` with `scope: "global"`.
- **Org default** (only visible to org admins) — single `<select>` with one extra option `"Use system default"` at the top, which sends `value: null`. Below the select, a hint line: when the org value is `null`, show *"Inherited from system default: General"*; otherwise show *"Active for everyone in this org."*

Both controls show toast confirmation on save and surface 4xx errors inline.

### `frontend/src/components/preflight/PreflightPanel.tsx`

Replace the hardcoded initial state on line 108:

```tsx
const [mode, setMode] = useState<string>('investigation')
```

with a value seeded from `GET /v3/settings/default_mode` (fetched once at mount via React Query or the existing `api` client). Until the request resolves, render the panel with `general` selected — switching the selection once the response lands is fine since the user hasn't interacted yet.

If the existing `'investigation'` literal is a separate concept (not one of the 4 bundled modes), preserve its handling but still apply the resolved default on top.

## Authorization

- `is_superadmin` — already represented as `is_admin && (some superadmin flag or seeded user)`; reuse whatever check `core_settings` write currently uses (audit during implementation; do not invent a new check).
- `is_admin` of the calling user's org — derived from `ui_users.role = 'admin' AND ui_users.org_id = caller.org_id`.

## Verification

### Unit
`get_default_mode_id` resolution table:
| org_settings | core_settings | expected |
|---|---|---|
| `lead_gen` | anything | `lead_gen` |
| `null` / missing | `kyc_edd` | `kyc_edd` |
| `null` / missing | `null` / missing | `general` |
| `bogus_id` | `lead_gen` | `lead_gen` (org value rejected) |
| `null` | `bogus_id` | `general` (global rejected) |

### API
- Non-admin → `PUT /v3/settings/default_mode` returns 403 for either scope.
- Org admin attempting `scope: global` returns 403.
- Unknown mode id returns 400 with the list of valid ids.
- `value: null` clears the row (subsequent `GET` shows `org_value: null`).

### E2E (Playwright)
1. Superadmin signs in, sets system default to `lead_gen`. User A (different org, no org override) opens Preflight → `lead_gen` is preselected.
2. Org admin of org X sets org default to `kyc_edd`. User B in org X opens Preflight → `kyc_edd` is preselected; system default is unchanged for user A.
3. Org admin clears the override → User B's preflight falls back to `lead_gen` (the global default).

## Out of scope

- GitHub OAuth login wiring (separate active workstream).
- Theme / retention / other future per-org settings — the `org_settings` table is built to host them, but no UI is added.
- Per-user defaults.
