# Title Classifier

A HACS custom integration that watches entity states, persists every observed title in HA's storage, and exposes a numeric "enum" sensor so automations can react to what's playing/active without hard-coding titles. The integration domain is `title_classifier`.

## Panel — Title Classifier

After installing Title Classifier, a **Title Classifier** sidebar entry (icon: tag-multiple) appears in Home Assistant. It requires admin access.

The panel shows a single flat table of all tracked titles across every watcher, with:

| Column | Notes |
|--------|-------|
| **Title** | Raw title string as seen on the entity. Read-only. Highlighted with a "current" badge when it is the active title right now. |
| **Source** | Watcher name (e.g. PS5, Discord, Music). |
| **Value** | Mapped enum 0–9. Click the value to edit inline; press **Enter** or click away to save, **Escape** to cancel. Unclassified titles (value = 0) are highlighted in amber. |
| **Last Seen** | Relative time since the title was last observed. |

### Filters

- **Source** dropdown — narrow the table to one watcher.
- **Unclassified only** checkbox — show only titles still at enum 0.
- **Search** text field — substring match against the title string (case-insensitive). Press Enter or click **Apply**.

### Sorting

Click any column header to sort by that column; click again to reverse direction. Default: **Last Seen** descending (most-recently-seen first).

### Pagination

When there are more than 100 entries the table is split into pages of 100. Use the page buttons or Prev/Next to navigate.

### Auto-refresh

The table refreshes automatically every 30 seconds. Click **↻ Refresh** to refresh immediately.

## Watcher configuration

Each watcher is a config entry created via **Settings → Devices & Services → Add Integration → Title Classifier**.

| Option | Description |
|--------|-------------|
| **Name** | Friendly name shown in the panel and used as the entity slug. |
| **Source entity** | The entity whose state/attributes are watched (e.g. `media_player.ps5`). |
| **Watcher type** | `game`, `media`, or `activity` — controls which attributes are checked for the title. |
| **Artist attribute** *(media only)* | Attribute to prepend as "Artist – Title". Defaults to `media_artist`. |
| **Retention days** *(optional)* | Entries not seen for this many days are removed by the `clear_old` service. |

## Adding new sources

1. Go to **Settings → Devices & Services → Title Classifier → Add entry**.
2. Choose the source entity to watch and the watcher type.
3. The integration starts recording titles immediately; they appear in the panel as they are observed.

## Sensors

Per watcher, three entities are created:

| Entity | Description |
|--------|-------------|
| `sensor.title_classifier_<name>_enum` | Current mapped enum (0–9). Use this in automations. |
| `sensor.title_classifier_<name>_raw` | Current raw title string (diagnostic). |
| `sensor.title_classifier_<name>_catalog` | Number of tracked titles; full catalog in attributes (diagnostic). |

## Services

| Service | Description |
|---------|-------------|
| `title_classifier.set_enum` | Map a specific title to an enum value. |
| `title_classifier.delete_entry` | Remove a title from storage. |
| `title_classifier.import_entries` | Bulk-import a list of `{key, enum}` mappings. |
| `title_classifier.clear_old` | Delete entries not seen for N days. |

## WebSocket API

All commands require an authenticated HA WebSocket connection.

| Command | Admin required | Description |
|---------|---------------|-------------|
| `title_classifier/list` | No | All watchers with full catalog (legacy panel command). |
| `title_classifier/set_enum` | No | Map title → enum. |
| `title_classifier/delete_entry` | No | Delete a title entry. |
| `title_classifier/import_entries` | No | Bulk-import mappings. |
| `title_classifier/get_sources` | **Yes** | List all watchers (name, entry_id, watcher_type). |
| `title_classifier/list_entries` | **Yes** | Flat list of all entries, optionally filtered by `source`, `unclassified`, `search`. |
| `title_classifier/update_entry` | **Yes** | Update enum for one entry (`entry_id`, `key`, `enum_value` 0–9). |

## Permissions

The panel itself is registered with `require_admin=True`, so only HA admin accounts can see or use it. The three new WebSocket commands (`title_classifier/get_sources`, `title_classifier/list_entries`, `title_classifier/update_entry`) also enforce the admin check server-side via `@websocket_api.require_admin`.

## Frontend caching note

HA caches the panel JS aggressively. After updating the integration, do a **hard refresh** (Ctrl+Shift+R / Cmd+Shift+R) or clear the browser cache if the panel UI does not reflect changes.
