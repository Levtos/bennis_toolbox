// Title Classifier panel
// Uses Home Assistant WebSocket commands for authenticated Title Classifier access.
// Number inputs are always visible; Save/Enter persists changes explicitly.

(() => {
if (customElements.get("title-classifier-panel")) return;

const STORAGE_KEY = "title-classifier-panel-state-v1";

class TitleClassifierPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass    = null;
    this._sources = [];
    this._entries = [];
    this._loading = false;
    this._timer   = null;

    this._filterSource       = "";
    this._filterUnclassified = false;
    this._filterSearch       = "";

    this._sortBy  = "last_seen";
    this._sortAsc = false;   // newest first by default

    this._page          = 1;
    this._pageSize      = 100;   // flat rows per page
    this._pageSizeGroup = 25;    // artist groups per page when grouped

    this._groupByArtist    = false;
    this._showLegend       = false;
    this._collapsedArtists = new Set();

    this._includeHidden = false;
    this._acQuery       = "";
    this._acResults     = [];
    this._acOpen        = false;
    this._acTimer       = null;

    this._loadState();
    this._lastRenderSignature = null;
  }

  // ── persistence ───────────────────────────────────────────────────────────

  _loadState() {
    try {
      const raw = window.localStorage?.getItem(STORAGE_KEY);
      if (!raw) return;
      const s = JSON.parse(raw);
      if (typeof s.filterSource       === "string")  this._filterSource       = s.filterSource;
      if (typeof s.filterUnclassified === "boolean") this._filterUnclassified = s.filterUnclassified;
      if (typeof s.filterSearch       === "string")  this._filterSearch       = s.filterSearch;
      if (typeof s.sortBy             === "string")  this._sortBy             = s.sortBy;
      if (typeof s.sortAsc            === "boolean") this._sortAsc            = s.sortAsc;
      if (typeof s.groupByArtist      === "boolean") this._groupByArtist      = s.groupByArtist;
      if (typeof s.showLegend         === "boolean") this._showLegend         = s.showLegend;
      if (typeof s.includeHidden      === "boolean") this._includeHidden      = s.includeHidden;
      if (Array.isArray(s.collapsedArtists))         this._collapsedArtists   = new Set(s.collapsedArtists);
    } catch { /* ignore corrupt state */ }
  }

  _saveState() {
    try {
      window.localStorage?.setItem(STORAGE_KEY, JSON.stringify({
        filterSource:       this._filterSource,
        filterUnclassified: this._filterUnclassified,
        filterSearch:       this._filterSearch,
        sortBy:             this._sortBy,
        sortAsc:            this._sortAsc,
        groupByArtist:      this._groupByArtist,
        showLegend:         this._showLegend,
        includeHidden:      this._includeHidden,
        collapsedArtists:   [...this._collapsedArtists],
      }));
    } catch { /* localStorage unavailable */ }
  }

  set hass(h) {
    this._hass = h;
    if (!this._loading && this._entries.length === 0) this._load();
  }

  connectedCallback() {
    this._render();
    this._timer = setInterval(() => this._loadEntries(), 30_000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  // ── WebSocket helper ──────────────────────────────────────────────────────

  async _ws(message) {
    if (!this._hass?.connection) throw new Error("Home Assistant connection unavailable");
    return this._hass.connection.sendMessagePromise(message);
  }

  // ── data loading ──────────────────────────────────────────────────────────

  async _load() {
    await Promise.all([this._loadSources(), this._loadEntries()]);
  }

  async _loadSources() {
    try {
      this._sources = await this._ws({ type: "title_classifier/get_sources" });
      if (this._filterSource && !this._sources.some(s => s.entry_id === this._filterSource)) {
        // saved source filter no longer exists — drop it silently
        this._filterSource = "";
        this._saveState();
      }
    } catch (err) {
      this._toast(`Quellen konnten nicht geladen werden: ${err.message}`, "error");
    }
    this._render();
  }

  async _loadEntries({ showLoading = false, resetPage = false } = {}) {
    if (!this._hass) return;
    this._loading = showLoading;
    this._setTableLoading(showLoading);
    try {
      const message = { type: "title_classifier/list_entries" };
      if (this._filterSource) message.source = this._filterSource;
      if (this._filterUnclassified) message.unclassified = true;
      if (this._filterSearch.trim()) message.search = this._filterSearch.trim();
      if (this._includeHidden) message.include_hidden = true;
      this._entries = await this._ws(message);
      if (resetPage) this._page = 1;
    } catch (err) {
      this._toast(`Laden fehlgeschlagen: ${err.message}`, "error");
    } finally {
      this._loading = false;
      this._setTableLoading(false);
      this._render();
    }
  }

  _setTableLoading(isLoading) {
    this.shadowRoot?.querySelector(".tw")?.classList.toggle("loading", isLoading);
  }

  // ── save — no full re-render, just update the input's baseline ────────────

  async _save(entryId, key, value, inputEl, buttonEl = null) {
    try {
      this._setSaving(inputEl, buttonEl, true);
      await this._ws({ type: "title_classifier/update_entry", entry_id: entryId, key, enum_value: value });
      const e = this._entries.find(e => e.entry_id === entryId && e.key === key);
      if (e) {
        const wasUnmapped = e.enum === 0;
        const wasHidden   = !!e.hidden;
        const nowUnmapped = value === 0;
        e.enum = value;
        if (value !== 0 && wasHidden) {
          // backend clears hidden_at on classify — reflect that locally
          e.hidden    = false;
          e.hidden_at = null;
        }
        const src = this._sources.find(s => s.entry_id === entryId);
        if (src) {
          if (wasUnmapped !== nowUnmapped) {
            src.unmapped_count = Math.max(0, (src.unmapped_count ?? 0) + (nowUnmapped ? 1 : -1));
          }
          if (value !== 0 && wasHidden) {
            src.hidden_count = Math.max(0, (src.hidden_count ?? 0) - 1);
          }
        }
      }
      inputEl.dataset.original = String(value);
      inputEl.value = String(value);
      this._setInputDirty(inputEl, buttonEl, false);
      this._flash(inputEl, "saved");
      this._toast("Wert gespeichert", "success");
    } catch (err) {
      this._toast(`Speichern fehlgeschlagen: ${err.message}`, "error");
      inputEl.value = inputEl.dataset.original;
      this._setInputDirty(inputEl, buttonEl, false);
      this._flash(inputEl, "err");
    } finally {
      this._setSaving(inputEl, buttonEl, false);
    }
  }

  _saveInput(inputEl) {
    const orig = parseInt(inputEl.dataset.original, 10);
    const val  = parseInt(inputEl.value, 10);
    const buttonEl = this.shadowRoot?.querySelector(
      `.save-row[data-eid="${CSS.escape(inputEl.dataset.eid)}"][data-key="${CSS.escape(inputEl.dataset.key)}"]`
    );
    if (isNaN(val)) { inputEl.value = orig; return; }
    if (val === orig) { this._setInputDirty(inputEl, buttonEl, false); return; }
    if (val < 0 || val > 9) {
      this._toast("Wert muss 0–9 sein", "error");
      inputEl.value = orig;
      this._setInputDirty(inputEl, buttonEl, false);
      return;
    }
    this._save(inputEl.dataset.eid, inputEl.dataset.key, val, inputEl, buttonEl);
  }

  _setInputDirty(inputEl, buttonEl, dirty) {
    inputEl.classList.toggle("dirty", dirty);
    if (buttonEl) buttonEl.disabled = !dirty;
  }

  _setSaving(inputEl, buttonEl, saving) {
    inputEl.disabled = saving;
    if (buttonEl) {
      buttonEl.disabled = saving || inputEl.value === inputEl.dataset.original;
      buttonEl.textContent = saving ? "…" : "Speichern";
    }
  }

  _flash(el, cls) {
    el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), 900);
  }

  // ── sorting ───────────────────────────────────────────────────────────────

  _sortedEntries() {
    const grouping = this._groupByArtist && this._isMediaSource();
    return [...this._entries].sort((a, b) => {
      if (grouping) {
        const ac = (this._artistFrom(a.key) ?? "").localeCompare(this._artistFrom(b.key) ?? "");
        if (ac !== 0) return ac;
      }
      let cmp;
      switch (this._sortBy) {
        case "key":  cmp = a.key.localeCompare(b.key); break;
        case "enum": cmp = a.enum - b.enum; break;
        default:     cmp = new Date(a.last_seen) - new Date(b.last_seen);
      }
      return this._sortAsc ? cmp : -cmp;
    });
  }

  _toggleSort(col) {
    if (this._sortBy === col) {
      this._sortAsc = !this._sortAsc;
    } else {
      this._sortBy  = col;
      this._sortAsc = col !== "last_seen";
    }
    this._saveState();
    this._render();
  }

  // ── artist helpers ────────────────────────────────────────────────────────

  _artistFrom(key) {
    const i = key.indexOf(" - ");
    return i >= 0 ? key.slice(0, i) : null;
  }

  _titleFrom(key) {
    const i = key.indexOf(" - ");
    return i >= 0 ? key.slice(i + 3) : key;
  }

  _isMediaSource() {
    if (this._filterSource) {
      const src = this._sources.find(s => s.entry_id === this._filterSource);
      return src?.watcher_type === "media";
    }
    return this._sources.some(s => s.watcher_type === "media");
  }

  _toggleArtist(artist) {
    if (this._collapsedArtists.has(artist)) this._collapsedArtists.delete(artist);
    else this._collapsedArtists.add(artist);
    this._saveState();
    this._render();
  }

  // ── autocomplete (find hidden entries) ────────────────────────────────────

  _acScheduleSearch(query) {
    clearTimeout(this._acTimer);
    this._acQuery = query;
    if (query.trim().length < 2) {
      this._acResults = [];
      this._acOpen    = false;
      this._renderAcDropdown();
      return;
    }
    this._acTimer = setTimeout(() => this._acSearch(query.trim()), 220);
  }

  async _acSearch(query) {
    try {
      const msg = {
        type: "title_classifier/list_entries",
        search: query,
        include_hidden: true,
        limit: 25,
      };
      if (this._filterSource) msg.source = this._filterSource;
      this._acResults = await this._ws(msg);
      this._acOpen    = true;
    } catch (err) {
      this._toast(`Suche fehlgeschlagen: ${err.message}`, "error");
      this._acResults = [];
      this._acOpen    = false;
    }
    this._renderAcDropdown();
  }

  _acClose() {
    this._acOpen    = false;
    this._acQuery   = "";
    this._acResults = [];
    this._renderAcDropdown();
    const inp = this.shadowRoot?.querySelector("#ac-input");
    if (inp) inp.value = "";
  }

  _acPick(entryId, key) {
    // Bring the picked entry into the main view by jumping to that source +
    // exact-match search and turning on hidden inclusion. The user can then
    // assign an enum like with any other row.
    this._filterSource       = entryId;
    this._filterSearch       = key;
    this._filterUnclassified = false;
    this._includeHidden      = true;
    this._page               = 1;
    this._saveState();
    this._acClose();
    this._loadEntries({ resetPage: true, showLoading: true });
    this._toast("Eintrag in die Liste geholt", "success");
  }

  _renderAcDropdown() {
    const dd = this.shadowRoot?.querySelector(".ac-dd");
    if (!dd) return;
    if (!this._acOpen || this._acResults.length === 0) {
      dd.hidden = true;
      dd.innerHTML = "";
      return;
    }
    dd.hidden = false;
    dd.innerHTML = this._acResults.map(r => `
      <div class="ac-item" data-watcher="${this._esc(r.watcher_type || "")}"
           data-eid="${this._esc(r.entry_id)}" data-key="${this._esc(r.key)}">
        <span class="ac-row">
          <span class="enum-dot" data-enum="${r.enum}"></span>
          <span class="ac-key">${this._esc(r.key)}</span>
        </span>
        <span class="ac-meta">
          ${this._esc(r.source_name)} · Wert ${r.enum}${r.hidden ? " · versteckt" : ""}
          · zuletzt ${this._rel(r.last_seen)}
        </span>
      </div>`).join("");
    dd.querySelectorAll(".ac-item").forEach(el => {
      el.addEventListener("mousedown", ev => {
        ev.preventDefault();
        this._acPick(el.dataset.eid, el.dataset.key);
      });
    });
  }

  // ── bulk hide unmapped ────────────────────────────────────────────────────

  async _hideUnmapped() {
    if (!this._filterSource) {
      this._toast("Bitte zuerst eine Source wählen", "error");
      return;
    }
    const src = this._sources.find(s => s.entry_id === this._filterSource);
    const n = src?.unmapped_count ?? 0;
    if (n === 0) {
      this._toast("Keine unklassifizierten Einträge zum Ausblenden", "info");
      return;
    }
    if (!window.confirm(`${n} unklassifizierte Einträge in „${src?.name ?? "?"}\" ausblenden?\n\nDie Einträge bleiben in der Datenbank — werden sie wieder gespielt, tauchen sie automatisch wieder auf.`)) {
      return;
    }
    try {
      const res = await this._ws({ type: "title_classifier/hide_unmapped", entry_id: this._filterSource });
      this._toast(`${res?.hidden ?? 0} Einträge ausgeblendet`, "success");
      await Promise.all([this._loadSources(), this._loadEntries({ showLoading: true })]);
    } catch (err) {
      this._toast(`Ausblenden fehlgeschlagen: ${err.message}`, "error");
    }
  }

  _setAllCollapsed(collapse) {
    if (!collapse) {
      this._collapsedArtists.clear();
    } else {
      this._collapsedArtists = new Set(
        this._entries.map(e => this._artistFrom(e.key) ?? "— Kein Künstler —")
      );
    }
    this._saveState();
    this._render();
  }

  // ── paginated view model ──────────────────────────────────────────────────

  _viewModel() {
    const sorted = this._sortedEntries();
    if (this._groupByArtist && this._isMediaSource()) {
      const seen  = new Map();
      const order = [];
      for (const e of sorted) {
        const artist = this._artistFrom(e.key) ?? "— Kein Künstler —";
        if (!seen.has(artist)) { seen.set(artist, []); order.push(artist); }
        seen.get(artist).push(e);
      }
      const groups = order.map(artist => ({
        artist,
        entries:   seen.get(artist),
        collapsed: this._collapsedArtists.has(artist),
      }));
      const totalPages = Math.max(1, Math.ceil(groups.length / this._pageSizeGroup));
      const page       = Math.min(this._page, totalPages);
      const pageGroups = groups.slice((page - 1) * this._pageSizeGroup, page * this._pageSizeGroup);
      return {
        mode: "grouped", groups: pageGroups,
        totalRows: sorted.length, totalGroups: groups.length,
        page, totalPages,
      };
    }
    const totalPages = Math.max(1, Math.ceil(sorted.length / this._pageSize));
    const page       = Math.min(this._page, totalPages);
    const rows       = sorted.slice((page - 1) * this._pageSize, page * this._pageSize);
    return { mode: "flat", rows, totalRows: sorted.length, page, totalPages };
  }

  // ── render ────────────────────────────────────────────────────────────────

  _render(force = false) {
    if (!this.shadowRoot) return;

    const view = this._viewModel();
    if (this._page !== view.page) this._page = view.page;
    const signature = this._renderSignature(view);
    if (!force && signature === this._lastRenderSignature) return;
    this._lastRenderSignature = signature;

    const arr = col =>
      this._sortBy !== col
        ? `<span class="sh">↕</span>`
        : `<span class="sa">${this._sortAsc ? "↑" : "↓"}</span>`;

    const showGroupBy = this._isMediaSource();

    this.shadowRoot.innerHTML = `
<style>
:host {
  display: block; padding: 24px;
  color: var(--primary-text-color);
  background: var(--primary-background-color);
  min-height: 100%; box-sizing: border-box;
  font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);

  /* Dracula-inspired enum palette in rainbow order (0 = neutral) */
  --tc-enum-0: #6272a4; /* comment grey-blue */
  --tc-enum-1: #ff5555; /* red */
  --tc-enum-2: #ffb86c; /* orange */
  --tc-enum-3: #f1fa8c; /* yellow */
  --tc-enum-4: #50fa7b; /* green */
  --tc-enum-5: #8be9fd; /* cyan */
  --tc-enum-6: #bd93f9; /* purple */
  --tc-enum-7: #ff79c6; /* pink */
  --tc-enum-8: #f8f8f2; /* foreground / white */
  --tc-enum-9: #44475a; /* dark selection */

  /* Watcher categories — left rail colour per source kind */
  --tc-cat-media:    #bd93f9;
  --tc-cat-game:     #50fa7b;
  --tc-cat-activity: #ffb86c;
}
h1 { margin: 0 0 20px; font-size: 1.5rem; font-weight: 400; }

/* toolbar */
.bar {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  margin-bottom: 14px; padding: 12px 16px;
  background: var(--card-background-color); border-radius: 8px;
  box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.12));
}
.fg { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
select, input[type="text"] {
  background: var(--input-fill-color, var(--secondary-background-color));
  border: 1px solid var(--input-ink-color, var(--secondary-text-color));
  border-radius: 4px; color: var(--primary-text-color);
  font: inherit; height: 34px; padding: 0 10px;
}
select             { min-width: 160px; }
input[type="text"] { min-width: 180px; }
input[type="checkbox"] { cursor: pointer; }
.btn {
  border: none; border-radius: 4px; cursor: pointer;
  font: inherit; height: 34px; padding: 0 14px; transition: opacity .15s;
}
.btn-p { background: var(--primary-color); color: var(--text-primary-color, #fff); }
.btn-g {
  background: transparent;
  border: 1px solid var(--divider-color);
  color: var(--primary-text-color);
}
.btn:hover { opacity: .85; }

/* legend */
.legend {
  display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 14px;
}
.leg-section {
  background: var(--card-background-color); border-radius: 8px;
  box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.12));
  flex: 1; min-width: 260px; padding: 14px 16px;
}
.leg-title {
  font-size: .85rem; font-weight: 600; letter-spacing: .04em;
  margin-bottom: 10px; text-transform: uppercase;
  color: var(--secondary-text-color);
}
.leg-table { border-collapse: collapse; font-size: .88rem; width: 100%; }
.leg-table th {
  border-bottom: 1px solid var(--divider-color);
  font-weight: 600; padding: 4px 10px 6px; text-align: left;
}
.leg-table td { padding: 5px 10px; border-bottom: 1px solid var(--divider-color); }
.leg-table tr:last-child td { border-bottom: none; }
.leg-enum {
  font-family: var(--code-font-family, monospace); font-weight: 700; width: 64px;
  display: flex; align-items: center; gap: 8px;
}
.leg-enum .enum-dot { width: 10px; height: 10px; }
.leg-cat-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.leg-cat-swatch { width: 14px; height: 14px; border-radius: 3px; }
.leg-mode { color: var(--secondary-text-color); font-family: var(--code-font-family, monospace); font-size: .82rem; }
.leg-reserviert td { color: var(--secondary-text-color); font-style: italic; }

/* info line */
.inf { margin-bottom: 8px; font-size: .85rem; color: var(--secondary-text-color); }
.inf b { color: var(--primary-text-color); font-weight: 600; }

/* table card */
.tw {
  background: var(--card-background-color); border-radius: 8px;
  box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.12));
  overflow-x: auto; transition: opacity .2s;
}
.tw.loading { opacity: .5; pointer-events: none; }
table { border-collapse: collapse; width: 100%; font-size: .94rem; }
thead th {
  background: var(--table-header-background-color, var(--secondary-background-color));
  border-bottom: 2px solid var(--divider-color);
  cursor: pointer; font-weight: 600; padding: 11px 16px;
  text-align: left; user-select: none; white-space: nowrap;
}
thead th:hover { filter: brightness(.95); }
.sh { opacity: .3; }
.sa { color: var(--primary-color); }
td  { border-bottom: 1px solid var(--divider-color); padding: 8px 16px; vertical-align: middle; }
tr:last-child td { border-bottom: none; }

/* artist group header — clickable for collapse/expand */
tr.artist-hdr td {
  background: var(--secondary-background-color);
  border-bottom: 1px solid var(--divider-color);
  border-left: 3px solid var(--primary-color);
  color: var(--primary-text-color);
  cursor: pointer;
  font-size: .85rem; font-weight: 600; padding: 6px 16px;
  user-select: none;
}
tr.artist-hdr td:hover { filter: brightness(1.05); }
tr.artist-hdr .caret {
  display: inline-block; width: 14px; text-align: center;
  margin-right: 6px; color: var(--secondary-text-color);
}
tr.artist-hdr.collapsed .caret { color: var(--primary-color); }
tr.artist-hdr .ct {
  margin-left: 8px; color: var(--secondary-text-color);
  font-weight: 400; font-size: .8rem;
}

/* row accents — left rail by watcher category */
tr[data-watcher="media"]    td:first-child { border-left: 3px solid var(--tc-cat-media);    }
tr[data-watcher="game"]     td:first-child { border-left: 3px solid var(--tc-cat-game);     }
tr[data-watcher="activity"] td:first-child { border-left: 3px solid var(--tc-cat-activity); }
tr.current { background: color-mix(in srgb, var(--primary-color) 7%, transparent); }

/* enum-value colour dot next to the number input */
.enum-dot {
  width: 12px; height: 12px; border-radius: 50%;
  background: var(--tc-enum-0);
  border: 1px solid color-mix(in srgb, currentColor 25%, transparent);
  flex-shrink: 0;
}
.enum-dot[data-enum="0"] { background: var(--tc-enum-0); }
.enum-dot[data-enum="1"] { background: var(--tc-enum-1); }
.enum-dot[data-enum="2"] { background: var(--tc-enum-2); }
.enum-dot[data-enum="3"] { background: var(--tc-enum-3); }
.enum-dot[data-enum="4"] { background: var(--tc-enum-4); }
.enum-dot[data-enum="5"] { background: var(--tc-enum-5); }
.enum-dot[data-enum="6"] { background: var(--tc-enum-6); }
.enum-dot[data-enum="7"] { background: var(--tc-enum-7); }
.enum-dot[data-enum="8"] { background: var(--tc-enum-8); }
.enum-dot[data-enum="9"] { background: var(--tc-enum-9); }

/* unclassified marker now lives on the input, not the row rail */
tr.zero .ei { border-color: var(--warning-color, #ffa600); }

/* cells */
.key {
  font-family: var(--code-font-family, monospace); font-size: .88rem;
  max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.badge {
  background: var(--primary-color); border-radius: 999px; color: #fff;
  font-size: .7rem; margin-left: 6px; padding: 1px 7px; vertical-align: middle;
}
.src {
  background: var(--secondary-background-color);
  border-radius: 4px; font-size: .8rem; padding: 2px 8px; white-space: nowrap;
}

/* always-visible number input for enum */
.ei {
  background: var(--input-fill-color, var(--secondary-background-color));
  border: 1px solid var(--divider-color);
  border-radius: 4px; color: var(--primary-text-color);
  font: 600 1rem/1 inherit; text-align: center;
  width: 62px; height: 30px; padding: 0;
  transition: border-color .18s, background .18s;
}
.enum-cell { display: flex; align-items: center; gap: 8px; }
.ei:focus { outline: none; border-color: var(--primary-color); }
.ei.dirty { border-color: var(--warning-color, #ffa600); }
.ei.saved {
  border-color: var(--success-color, #4caf50);
  background: color-mix(in srgb, var(--success-color, #4caf50) 14%, transparent);
}
.ei.err {
  border-color: var(--error-color, #f44336);
  background: color-mix(in srgb, var(--error-color, #f44336) 14%, transparent);
}
.save-row { height: 30px; padding: 0 10px; }
.save-row:disabled { cursor: default; opacity: .45; }

/* pagination */
.pag {
  display: flex; align-items: center; justify-content: center;
  flex-wrap: wrap; gap: 6px; margin-top: 14px;
}
.pag .btn { min-width: 36px; padding: 0 8px; }
.pag .act { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }

/* hidden-row dimming when "Versteckte zeigen" is on */
tr.is-hidden td { opacity: .55; }
tr.is-hidden td .src,
tr.is-hidden td .key { font-style: italic; }

/* autocomplete row */
.ac-bar {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 14px;
}
.ac-wrap { position: relative; flex: 1; min-width: 240px; max-width: 520px; }
.ac-wrap input {
  background: var(--input-fill-color, var(--secondary-background-color));
  border: 1px solid var(--input-ink-color, var(--secondary-text-color));
  border-radius: 4px; color: var(--primary-text-color);
  font: inherit; height: 34px; padding: 0 10px; width: 100%; box-sizing: border-box;
}
.ac-hint {
  color: var(--secondary-text-color); font-size: .8rem;
}
.ac-dd {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 50;
  background: var(--card-background-color);
  border: 1px solid var(--divider-color); border-radius: 4px;
  margin-top: 2px; max-height: 320px; overflow-y: auto;
  box-shadow: 0 4px 14px rgba(0,0,0,.25);
}
.ac-item {
  cursor: pointer; padding: 8px 12px 8px 9px;
  border-bottom: 1px solid var(--divider-color);
  border-left: 3px solid transparent;
  display: flex; flex-direction: column; gap: 2px;
}
.ac-item[data-watcher="media"]    { border-left-color: var(--tc-cat-media); }
.ac-item[data-watcher="game"]     { border-left-color: var(--tc-cat-game); }
.ac-item[data-watcher="activity"] { border-left-color: var(--tc-cat-activity); }
.ac-item:last-child  { border-bottom: none; }
.ac-item:hover       { background: var(--secondary-background-color); }
.ac-row { display: flex; align-items: center; gap: 8px; }
.ac-key  { font-family: var(--code-font-family, monospace); font-size: .88rem; }
.ac-meta { color: var(--secondary-text-color); font-size: .75rem; }

/* empty state */
.empty { color: var(--secondary-text-color); padding: 40px; text-align: center; }

/* toast */
.toast {
  animation: tin .2s ease; border-radius: 8px;
  bottom: 28px; box-shadow: 0 4px 14px rgba(0,0,0,.25);
  color: #fff; font-size: .9rem; max-width: 320px;
  padding: 12px 20px; position: fixed; right: 28px; z-index: 9999;
  background: var(--primary-color);
}
.toast.error   { background: var(--error-color,   #f44336); }
.toast.success { background: var(--success-color, #4caf50); }
@keyframes tin { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
</style>

<h1>Title Classifier</h1>

<div class="bar">
  <div class="fg">
    Source
    <select id="f-src">
      <option value="">${this._esc(this._allSourcesLabel())}</option>
      ${this._sources.map(s => {
        const label = `${s.name} (${s.entry_count ?? 0})`;
        return `<option value="${this._esc(s.entry_id)}"${this._filterSource === s.entry_id ? " selected" : ""}>${this._esc(label)}</option>`;
      }).join("")}
    </select>
  </div>
  <div class="fg">
    <input type="checkbox" id="f-unc"${this._filterUnclassified ? " checked" : ""} />
    <label for="f-unc">Nur unklassifiziert</label>
  </div>
  <div class="fg">
    <input type="text" id="f-s" placeholder="Titel suchen …" value="${this._esc(this._filterSearch)}" />
  </div>
  <button class="btn btn-p" id="btn-apply">Filter anwenden</button>
  <button class="btn btn-g" id="btn-ref" title="Jetzt aktualisieren">↻</button>
  ${showGroupBy ? `
  <div class="fg">
    <input type="checkbox" id="f-grp"${this._groupByArtist ? " checked" : ""} />
    <label for="f-grp">Nach Künstler</label>
  </div>` : ""}
  ${showGroupBy && this._groupByArtist ? `
  <button class="btn btn-g" id="btn-coll-all" title="Alle Künstler einklappen">Alle ▸</button>
  <button class="btn btn-g" id="btn-exp-all"  title="Alle Künstler ausklappen">Alle ▾</button>` : ""}
  ${this._anyAutoHide() ? `
  <div class="fg">
    <input type="checkbox" id="f-hid"${this._includeHidden ? " checked" : ""} />
    <label for="f-hid">Versteckte zeigen</label>
  </div>` : ""}
  ${this._hideButtonHtml()}
  <button class="btn btn-g" id="btn-leg">${this._showLegend ? "Legende ▴" : "Legende ▾"}</button>
</div>

${this._acBarHtml()}

${this._showLegend ? this._legendHtml() : ""}

<div class="inf">${this._totalsLine(view)}</div>

<div class="tw${this._loading ? " loading" : ""}">
  <table>
    <thead>
      <tr>
        <th id="th-k">Titel ${arr("key")}</th>
        <th>Source</th>
        <th id="th-e" style="width:180px">Wert ${arr("enum")}</th>
        <th id="th-l">Zuletzt ${arr("last_seen")}</th>
      </tr>
    </thead>
    <tbody>
      ${this._bodyHtml(view)}
    </tbody>
  </table>
</div>

${view.totalPages > 1 ? this._pagHtml(view.page, view.totalPages) : ""}
`;

    this._wire(view.page, view.totalPages);
  }

  _allSourcesLabel() {
    const total = this._sources.reduce((sum, s) => sum + (s.entry_count ?? 0), 0);
    return total ? `Alle (${total})` : "Alle";
  }

  _anyAutoHide() {
    return this._sources.some(s => (s.auto_hide_hours ?? 0) > 0 || (s.hidden_count ?? 0) > 0);
  }

  _hiddenCount() {
    const src = this._sources.find(s => s.entry_id === this._filterSource);
    return this._filterSource
      ? src?.hidden_count ?? 0
      : this._sources.reduce((sum, s) => sum + (s.hidden_count ?? 0), 0);
  }

  _hideButtonHtml() {
    if (!this._filterSource) return "";
    const src = this._sources.find(s => s.entry_id === this._filterSource);
    const n = src?.unmapped_count ?? 0;
    if (n === 0) return "";
    return `<button class="btn btn-g" id="btn-hide" title="Unklassifizierte Einträge dieser Source ausblenden">Ausblenden (${n})</button>`;
  }

  _acBarHtml() {
    if (!this._anyAutoHide()) return "";
    const hidden = this._hiddenCount();
    return `
<div class="ac-bar">
  <div class="ac-wrap">
    <input type="text" id="ac-input" placeholder="Eintrag vervollständigen — versteckte Titel suchen …"
           value="${this._esc(this._acQuery)}" autocomplete="off" />
    <div class="ac-dd" hidden></div>
  </div>
  <span class="ac-hint">${hidden} ausgeblendet · tippen zum Suchen, Klick holt zurück</span>
</div>`;
  }

  _totalsLine(view) {
    if (this._loading) return "Lädt …";
    const src = this._sources.find(s => s.entry_id === this._filterSource);
    const totalEntries = this._filterSource
      ? src?.entry_count ?? 0
      : this._sources.reduce((sum, s) => sum + (s.entry_count ?? 0), 0);
    const totalUnmapped = this._filterSource
      ? src?.unmapped_count ?? 0
      : this._sources.reduce((sum, s) => sum + (s.unmapped_count ?? 0), 0);

    const word         = view.totalRows === 1 ? "Eintrag" : "Einträge";
    const filteredHint = view.totalRows !== totalEntries
      ? ` (gefiltert aus <b>${totalEntries}</b>)` : "";
    const groupHint    = view.mode === "grouped" ? ` · ${view.totalGroups} Künstler` : "";
    const pageHint     = view.totalPages > 1 ? ` · Seite ${view.page}/${view.totalPages}` : "";
    const unmappedHint = totalUnmapped ? ` · <b>${totalUnmapped}</b> unklassifiziert` : "";
    const hiddenCount  = this._hiddenCount();
    const hiddenHint   = hiddenCount
      ? ` · <b>${hiddenCount}</b> ${this._includeHidden ? "ausgeblendet (sichtbar)" : "ausgeblendet"}`
      : "";

    return `<b>${view.totalRows}</b> ${word}${filteredHint}${groupHint}${pageHint}${unmappedHint}${hiddenHint}`;
  }

  // ── body / row rendering ──────────────────────────────────────────────────

  _bodyHtml(view) {
    if (view.totalRows === 0) {
      return `<tr><td class="empty" colspan="4">${this._loading ? "Lädt …" : "Keine Einträge gefunden."}</td></tr>`;
    }
    if (view.mode === "flat") {
      return view.rows.map(e => this._rowHtml(e, e.key)).join("");
    }
    let html = "";
    for (const g of view.groups) {
      const caret = g.collapsed ? "▸" : "▾";
      const stats = this._groupStats(g.entries);
      html += `<tr class="artist-hdr${g.collapsed ? " collapsed" : ""}" data-artist="${this._esc(g.artist)}">`
            + `<td colspan="4"><span class="caret">${caret}</span>${this._esc(g.artist)}`
            + `<span class="ct">${g.entries.length} Titel${stats}</span></td></tr>`;
      if (!g.collapsed) {
        html += g.entries.map(e => this._rowHtml(e, this._titleFrom(e.key))).join("");
      }
    }
    return html;
  }

  _groupStats(entries) {
    const unmapped = entries.filter(e => e.enum === 0).length;
    if (unmapped === 0)              return " · alle klassifiziert";
    if (unmapped === entries.length) return " · alle unklassifiziert";
    return ` · ${unmapped} unklassifiziert`;
  }

  _rowHtml(e, displayKey) {
    const cls = [
      e.enum === 0 ? "zero" : "",
      e.is_current ? "current" : "",
      e.hidden ? "is-hidden" : "",
    ].filter(Boolean).join(" ");
    const watcher = this._esc(e.watcher_type || "");
    return `<tr class="${cls}" data-watcher="${watcher}">
  <td class="key">${this._esc(displayKey)}${e.is_current ? '<span class="badge">aktiv</span>' : ""}</td>
  <td><span class="src">${this._esc(e.source_name)}</span></td>
  <td>
    <div class="enum-cell">
      <span class="enum-dot" data-enum="${e.enum}"></span>
      <input class="ei" type="number" min="0" max="9" step="1"
             value="${e.enum}" data-original="${e.enum}"
             data-eid="${this._esc(e.entry_id)}" data-key="${this._esc(e.key)}" />
      <button class="btn btn-g save-row" disabled
              data-eid="${this._esc(e.entry_id)}" data-key="${this._esc(e.key)}">Speichern</button>
    </div>
  </td>
  <td>${this._rel(e.last_seen)}</td>
</tr>`;
  }

  // ── legend ────────────────────────────────────────────────────────────────

  _legendHtml() {
    const MEDIA = [
      [0,     "normal",         "Kein besonderer Eingriff"],
      [1,     "boost",          "Lieblingstitel → Track Boost +0.15"],
      [2,     "mute",           "Unerwünschter Titel → Lautstärke 0"],
      ["3–9", "Reserviert",     "Zukünftige Erweiterungen"],
    ];
    const GAME = [
      [0,     "gaming_default", "Unklassifiziert, Standard-Routing"],
      [1,     "gaming_grind",   "Grinding-Modus, Musik dominant"],
      [2,     "gaming_headset", "Headset-Modus, immersives Spiel"],
      ["3–9", "Reserviert",     "Zukünftige Erweiterungen"],
    ];

    const selectedSrc = this._sources.find(s => s.entry_id === this._filterSource);
    const types = new Set(
      selectedSrc ? [selectedSrc.watcher_type] : this._sources.map(s => s.watcher_type)
    );

    const enumCell = (e) => {
      if (typeof e === "string") return `<td class="leg-enum">${e}</td>`;
      return `<td class="leg-enum"><span class="enum-dot" data-enum="${e}"></span>${e}</td>`;
    };

    const table = (legend, title) => `
<div class="leg-section">
  <div class="leg-title">${title}</div>
  <table class="leg-table">
    <thead><tr><th>Enum</th><th>Modus</th><th>Bedeutung</th></tr></thead>
    <tbody>
      ${legend.map(([e, m, d]) =>
        `<tr${typeof e === "string" ? ' class="leg-reserviert"' : ""}>`
        + enumCell(e)
        + `<td class="leg-mode">${this._esc(m)}</td>`
        + `<td>${this._esc(d)}</td></tr>`
      ).join("")}
    </tbody>
  </table>
</div>`;

    const catLabels = { media: "Media", game: "Game / Gaming", activity: "Activity" };
    const catRows = [...types]
      .filter(t => catLabels[t])
      .map(t => `<div class="leg-cat-row"><span class="leg-cat-swatch" style="background: var(--tc-cat-${t})"></span>${catLabels[t]}</div>`)
      .join("");
    const catSection = catRows
      ? `<div class="leg-section"><div class="leg-title">Kategorie-Streifen</div>${catRows}</div>`
      : "";

    const sections = [];
    if (catSection)                                   sections.push(catSection);
    if (types.has("media") || types.has("activity")) sections.push(table(MEDIA, "Media"));
    if (types.has("game"))                            sections.push(table(GAME,  "Game / Gaming"));

    return sections.length ? `<div class="legend">${sections.join("")}</div>` : "";
  }

  _pagHtml(page, n) {
    const MAX = 9;
    let s = Math.max(1, page - Math.floor(MAX / 2));
    const e = Math.min(n, s + MAX - 1);
    if (e - s < MAX - 1) s = Math.max(1, e - MAX + 1);
    const btns = [];
    if (s > 1) btns.push(`<button class="btn btn-g pb" data-p="1">1</button><span>…</span>`);
    for (let p = s; p <= e; p++)
      btns.push(`<button class="btn btn-g${p === page ? " act" : ""} pb" data-p="${p}">${p}</button>`);
    if (e < n) btns.push(`<span>…</span><button class="btn btn-g pb" data-p="${n}">${n}</button>`);
    return `
<div class="pag">
  <button class="btn btn-g" id="pg-p" ${page <= 1 ? "disabled" : ""}>← Zurück</button>
  ${btns.join("")}
  <button class="btn btn-g" id="pg-n" ${page >= n ? "disabled" : ""}>Weiter →</button>
</div>`;
  }

  // ── event wiring ──────────────────────────────────────────────────────────

  _wire(page, totalPages) {
    const r = this.shadowRoot;

    // filter bar
    r.querySelector("#btn-apply")?.addEventListener("click", () => {
      this._filterSource       = r.querySelector("#f-src")?.value ?? "";
      this._filterUnclassified = r.querySelector("#f-unc")?.checked ?? false;
      this._filterSearch       = r.querySelector("#f-s")?.value ?? "";
      this._saveState();
      this._loadEntries({ resetPage: true });
    });
    r.querySelector("#f-s")?.addEventListener("keydown", ev => {
      if (ev.key === "Enter") r.querySelector("#btn-apply")?.click();
    });
    r.querySelector("#btn-ref")?.addEventListener("click", () => this._loadEntries({ showLoading: true }));

    // legend toggle
    r.querySelector("#btn-leg")?.addEventListener("click", () => {
      this._showLegend = !this._showLegend;
      this._saveState();
      this._render();
    });

    // group-by-artist toggle
    r.querySelector("#f-grp")?.addEventListener("change", ev => {
      this._groupByArtist = ev.target.checked;
      this._page = 1;
      this._saveState();
      this._render();
    });

    // collapse / expand all artists
    r.querySelector("#btn-coll-all")?.addEventListener("click", () => this._setAllCollapsed(true));
    r.querySelector("#btn-exp-all") ?.addEventListener("click", () => this._setAllCollapsed(false));

    // "Versteckte zeigen" toggle
    r.querySelector("#f-hid")?.addEventListener("change", ev => {
      this._includeHidden = ev.target.checked;
      this._saveState();
      this._loadEntries({ showLoading: true });
    });

    // bulk hide unmapped for the current source
    r.querySelector("#btn-hide")?.addEventListener("click", () => this._hideUnmapped());

    // autocomplete input (find hidden entries by typing)
    const acInput = r.querySelector("#ac-input");
    if (acInput) {
      acInput.addEventListener("input", ev => this._acScheduleSearch(ev.target.value));
      acInput.addEventListener("focus", () => {
        if (this._acResults.length > 0) { this._acOpen = true; this._renderAcDropdown(); }
      });
      acInput.addEventListener("blur", () => {
        // delay close so mousedown on a dropdown item can fire first
        setTimeout(() => { this._acOpen = false; this._renderAcDropdown(); }, 150);
      });
      acInput.addEventListener("keydown", ev => {
        if (ev.key === "Escape") this._acClose();
      });
      // Restore dropdown state across re-renders.
      if (this._acOpen) this._renderAcDropdown();
    }

    // artist header → toggle this group
    r.querySelectorAll("tr.artist-hdr").forEach(row => {
      row.addEventListener("click", () => this._toggleArtist(row.dataset.artist));
    });

    // sortable headers
    r.querySelector("#th-k")?.addEventListener("click", () => this._toggleSort("key"));
    r.querySelector("#th-e")?.addEventListener("click", () => this._toggleSort("enum"));
    r.querySelector("#th-l")?.addEventListener("click", () => this._toggleSort("last_seen"));

    // enum inputs — explicit save button; blur validates
    r.querySelectorAll(".ei").forEach(inp => {
      const btn = r.querySelector(
        `.save-row[data-eid="${CSS.escape(inp.dataset.eid)}"][data-key="${CSS.escape(inp.dataset.key)}"]`
      );
      const dot = inp.parentElement?.querySelector(".enum-dot");
      inp.addEventListener("input", () => {
        this._setInputDirty(inp, btn, inp.value !== inp.dataset.original);
        if (dot) {
          const v = parseInt(inp.value, 10);
          dot.dataset.enum = (Number.isInteger(v) && v >= 0 && v <= 9) ? String(v) : "0";
        }
      });
      inp.addEventListener("blur", () => {
        const orig = parseInt(inp.dataset.original, 10);
        const val  = parseInt(inp.value, 10);
        if (isNaN(val))         { inp.value = orig; return; }
        if (val === orig)       return;
        if (val < 0 || val > 9) {
          this._toast("Wert muss 0–9 sein", "error");
          inp.value = orig;
          return;
        }
      });
    });
    r.querySelectorAll(".save-row").forEach(btn => {
      btn.addEventListener("click", () => {
        const inp = r.querySelector(
          `.ei[data-eid="${CSS.escape(btn.dataset.eid)}"][data-key="${CSS.escape(btn.dataset.key)}"]`
        );
        if (inp) this._saveInput(inp);
      });
    });

    // pagination
    r.querySelectorAll(".pb").forEach(b =>
      b.addEventListener("click", () => { this._page = +b.dataset.p; this._render(); })
    );
    r.querySelector("#pg-p")?.addEventListener("click", () => {
      if (this._page > 1) { this._page--; this._render(); }
    });
    r.querySelector("#pg-n")?.addEventListener("click", () => {
      if (this._page < totalPages) { this._page++; this._render(); }
    });
  }

  // ── utilities ─────────────────────────────────────────────────────────────

  _renderSignature(view) {
    return JSON.stringify({
      sources:            this._sources,
      entries:            this._entries,
      filterSource:       this._filterSource,
      filterUnclassified: this._filterUnclassified,
      filterSearch:       this._filterSearch,
      sortBy:             this._sortBy,
      sortAsc:            this._sortAsc,
      groupByArtist:      this._groupByArtist,
      showLegend:         this._showLegend,
      includeHidden:      this._includeHidden,
      acQuery:            this._acQuery,
      collapsed:          [...this._collapsedArtists],
      mode:               view.mode,
      page:               view.page,
      loading:            this._loading,
    });
  }

  _toast(msg, type = "info") {
    this.shadowRoot?.querySelectorAll(".toast").forEach(t => t.remove());
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = msg;
    this.shadowRoot.appendChild(el);
    setTimeout(() => el.remove(), 3500);
  }

  _rel(iso) {
    if (!iso) return "—";
    const s = Math.floor(Math.abs(Date.now() - new Date(iso)) / 1000);
    if (isNaN(s))   return iso;
    if (s < 60)     return `${s}s`;
    if (s < 3600)   return `${Math.floor(s / 60)}m`;
    if (s < 86400)  return `${Math.floor(s / 3600)}h`;
    return `${Math.floor(s / 86400)}d`;
  }

  _esc(v) {
    return String(v ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
}

customElements.define("title-classifier-panel", TitleClassifierPanel);
})();
