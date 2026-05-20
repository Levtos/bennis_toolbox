// Wake Planner panel — talks to the integration over the WebSocket API.
//
// All persistent config (people, rules, global settings) is stored in the
// config entry and edited from here. The Python side exposes the
// `wake_planner/*` WS commands implemented in websocket_api.py.

const WEEKDAYS = [
  { idx: 0, short: "Mon", long: "Monday" },
  { idx: 1, short: "Tue", long: "Tuesday" },
  { idx: 2, short: "Wed", long: "Wednesday" },
  { idx: 3, short: "Thu", long: "Thursday" },
  { idx: 4, short: "Fri", long: "Friday" },
  { idx: 5, short: "Sat", long: "Saturday" },
  { idx: 6, short: "Sun", long: "Sunday" },
];

const STYLES = `
:host { display:block; padding:16px 20px 40px; color:var(--primary-text-color); background:var(--primary-background-color); font-family:var(--paper-font-body1_-_font-family,system-ui); }
header { display:flex; align-items:center; gap:12px; margin-bottom:18px; flex-wrap:wrap; }
header h1 { margin:0; font-size:20px; font-weight:700; }
.tabs { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:18px; }
.tab { background:var(--card-background-color); color:var(--primary-text-color); border:0; border-radius:14px; padding:9px 16px; min-height:38px; box-shadow:var(--ha-card-box-shadow,0 1px 3px #0002); cursor:pointer; font-size:13px; font-weight:600; }
.tab.active { background:var(--primary-color); color:var(--text-primary-color,#fff); }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }
ha-card, .card { display:block; border-radius:16px; padding:16px 18px; background:var(--card-background-color); box-shadow:var(--ha-card-box-shadow,0 1px 3px #0002); margin-bottom:14px; }
.card h2 { margin:0 0 8px; font-size:17px; font-weight:700; }
.muted { opacity:.65; font-size:12px; }
.row { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.space { flex:1; }
.badge { display:inline-flex; align-items:center; border-radius:999px; padding:4px 10px; font-weight:700; text-transform:uppercase; font-size:11px; letter-spacing:.04em; }
.b-scheduled { background:#1b5e20; color:#fff; }
.b-skipped { background:#616161; color:#fff; }
.b-overridden { background:#ef6c00; color:#fff; }
.b-holiday { background:#b71c1c; color:#fff; }
.b-inactive { background:#37474f; color:#fff; }
.b-calendar { background:#0277bd; color:#fff; }
.time { font-size:clamp(40px,9vw,60px); font-weight:800; letter-spacing:-0.04em; margin:6px 0 4px; line-height:1; }
.reason { opacity:.8; font-size:13px; margin:8px 0 12px; }
button.btn { background:var(--card-background-color); color:var(--primary-text-color); border:1px solid var(--divider-color); border-radius:10px; padding:8px 12px; font-size:13px; cursor:pointer; min-height:38px; transition:background-color .2s, color .2s, border-color .2s, transform .08s; }
button.btn:active { transform:scale(0.97); }
button.btn.primary { background:var(--primary-color); color:var(--text-primary-color,#fff); border-color:transparent; font-weight:600; }
button.btn.danger { background:#b71c1c; color:#fff; border-color:transparent; }
button.btn.state-skip { background:#2e7d32; color:#fff; border-color:transparent; font-weight:600; }
button.btn.state-override { background:#ef6c00; color:#fff; border-color:transparent; font-weight:600; }
button.btn.flash-success { animation: wp-flash-success .9s ease-out; }
button.btn.flash-error { animation: wp-flash-error .9s ease-out; }
@keyframes wp-flash-success {
  0%   { background:#2e7d32; color:#fff; box-shadow:0 0 0 0 #2e7d3266; }
  40%  { background:#2e7d32; color:#fff; box-shadow:0 0 0 12px transparent; }
  100% { box-shadow:none; }
}
@keyframes wp-flash-error {
  0%, 60% { background:#b71c1c; color:#fff; }
  100% {}
}
button.btn:hover { filter:brightness(1.08); }
button.icon-btn { background:transparent; border:0; color:inherit; cursor:pointer; padding:6px 8px; border-radius:8px; font-size:16px; }
button.icon-btn:hover { background:var(--divider-color); }
.busy { pointer-events:none; opacity:.6; }
.spinner { display:inline-block; width:14px; height:14px; border:2px solid currentColor; border-right-color:transparent; border-radius:50%; animation:wp-spin 0.7s linear infinite; vertical-align:-2px; margin-right:6px; }
@keyframes wp-spin { to { transform:rotate(360deg); } }
input[type=text], input[type=time], input[type=number], input[type=date], select, textarea {
  background:var(--secondary-background-color); color:var(--primary-text-color);
  border:1px solid var(--divider-color); border-radius:8px; padding:8px 10px; font-size:14px;
  font-family:inherit; box-sizing:border-box;
}
input[type=checkbox] { width:18px; height:18px; cursor:pointer; accent-color:var(--primary-color); }
label.field { display:flex; flex-direction:column; gap:4px; font-size:12px; opacity:.85; }
label.field span.label { font-weight:600; opacity:.7; text-transform:uppercase; letter-spacing:.04em; font-size:11px; }
.rule-card { border:1px solid var(--divider-color); border-radius:14px; padding:14px; margin-bottom:10px; background:var(--secondary-background-color); }
.rule-card.disabled { opacity:.55; }
.rule-head { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.rule-title { font-weight:700; font-size:15px; flex:1; }
.rule-prio { font-size:11px; opacity:.6; padding:2px 6px; border-radius:6px; background:var(--card-background-color); }
.weekday-toggle { display:inline-flex; gap:4px; flex-wrap:wrap; }
.weekday-toggle label { display:inline-flex; align-items:center; gap:4px; padding:6px 9px; border-radius:8px; background:var(--card-background-color); cursor:pointer; font-size:12px; user-select:none; }
.weekday-toggle label.on { background:var(--primary-color); color:var(--text-primary-color,#fff); font-weight:600; }
.weekday-toggle label input { display:none; }
.cal-grid { display:grid; grid-template-columns:repeat(7,minmax(80px,1fr)); gap:4px; }
.cal-day { border:1px solid var(--divider-color); border-radius:10px; padding:8px; min-height:84px; font-size:12px; }
.cal-day.today { border-color:var(--primary-color); border-width:2px; }
.cal-day.weekend { background:var(--secondary-background-color); }
.cal-date { font-weight:700; font-size:14px; }
.cal-wake { margin-top:4px; font-weight:600; font-size:13px; }
.cal-wake.skip { opacity:.45; }
.cal-evt { font-size:11px; opacity:.65; margin-top:2px; }
.cal-scroll { overflow-x:auto; }
section.settings-section { padding:14px 0; border-top:1px solid var(--divider-color); }
section.settings-section:first-of-type { border-top:0; padding-top:0; }
section.settings-section h3 { margin:0 0 4px; font-size:14px; font-weight:700; }
.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; z-index:9999; padding:16px; }
.modal { background:var(--card-background-color); color:var(--primary-text-color); border-radius:16px; padding:24px; max-width:560px; width:100%; max-height:90vh; overflow-y:auto; box-shadow:0 8px 32px #0006; }
.modal h2 { margin:0 0 16px; font-size:18px; }
.modal-actions { display:flex; gap:8px; justify-content:flex-end; margin-top:20px; }
.toast { position:fixed; bottom:20px; left:50%; transform:translateX(-50%); background:#222; color:#fff; padding:10px 18px; border-radius:12px; font-size:13px; z-index:10000; opacity:0; transition:opacity .2s; }
.toast.show { opacity:1; }
.toast.error { background:#b71c1c; }
.empty { text-align:center; padding:40px 20px; opacity:.6; }
.toolbar-actions { display:flex; gap:8px; margin-left:auto; }
@media (max-width:720px) { :host { padding:8px 12px 32px; } .cal-grid { grid-template-columns:repeat(7,minmax(60px,1fr)); } }
`;

class WakePlannerPanel extends HTMLElement {
  constructor() {
    super();
    this._state = null;
    this._tab = "today";
    this._calendarEvents = {};
    this._loaded = false;
    this._busy = false;
    this._editingPerson = null; // slug of person currently being edited in rule editor
  }

  set hass(hass) {
    const wasHass = !!this._hass;
    this._hass = hass;
    if (!wasHass) this._initialFetch();
    // Intentionally no re-render on every hass tick: HA pushes state updates
    // many times per second, which would steal focus from inputs the user is
    // typing into. The panel re-renders only after its own actions
    // (_ws / _refresh / tab switch).
  }

  connectedCallback() {
    if (!this._delegated) {
      this.addEventListener("click", this._onDelegatedClick.bind(this));
      this.addEventListener("change", this._onDelegatedChange.bind(this));
      this._delegated = true;
    }
    if (this._hass && !this._loaded) this._initialFetch();
  }

  _onDelegatedClick(e) {
    const tabEl = e.target.closest("[data-tab]");
    if (tabEl && this.contains(tabEl)) {
      const tab = tabEl.dataset.tab;
      if (this._tab !== tab) {
        this._tab = tab;
        if (this._tab === "calendar") this._loadCalendarData().then(() => this._renderShell());
        else this._renderShell();
      }
      return;
    }
    const actionEl = e.target.closest("[data-action]");
    if (actionEl && this.contains(actionEl)) this._handleAction(actionEl, e);
  }

  _onDelegatedChange(e) {
    // Visual feedback for weekday toggles (no save, just toggling chip color)
    const wd = e.target.closest("[data-rule-wd]");
    if (wd && this.contains(wd)) {
      wd.closest("label").classList.toggle("on", wd.checked);
    }
  }

  async _initialFetch() {
    try {
      await this._refresh();
    } catch (e) {
      this._toast(`Failed to load: ${e.message || e}`, true);
      this._loaded = true;
      this._renderShell();
    }
  }

  async _refresh() {
    if (!this._hass) return;
    this._state = await this._hass.callWS({ type: "wake_planner/get_state" });
    this._loaded = true;
    if (this._tab === "calendar") await this._loadCalendarData();
    this._renderShell();
  }

  async _loadCalendarData() {
    await Promise.all([this._loadSchedule(), this._loadCalendarEvents()]);
  }

  async _loadSchedule() {
    try {
      const res = await this._hass.callWS({ type: "wake_planner/get_schedule", days: 14 });
      const map = {};
      for (const day of (res?.schedule || [])) map[day.date] = day;
      this._schedule = map;
    } catch (e) {
      this._schedule = {};
    }
  }

  async _ws(type, payload = {}) {
    if (this._busy) return null;
    this._busy = true;
    try {
      const result = await this._hass.callWS({ type, ...payload });
      if (result && result.persons) this._state = result;
      return result;
    } catch (e) {
      this._toast(e.message || String(e), true);
      return null;
    } finally {
      this._busy = false;
    }
  }

  _flashSuccess(btn) {
    if (!btn) return;
    btn.classList.remove("flash-success");
    // force reflow to restart the animation
    void btn.offsetWidth; // eslint-disable-line no-unused-expressions
    btn.classList.add("flash-success");
    setTimeout(() => btn.classList.remove("flash-success"), 900);
  }

  _updateTodayCard(slug) {
    const person = (this._state?.persons || []).find(p => p.slug === slug);
    if (!person) return;
    const old = this.querySelector(`[data-today-card="${slug}"]`);
    if (!old) return;
    const wrap = document.createElement("div");
    wrap.innerHTML = this._renderToday(person);
    const next = wrap.firstElementChild;
    if (next) old.replaceWith(next);
  }

  _updatePersonCard(slug) {
    const person = (this._state?.persons || []).find(p => p.slug === slug);
    const old = this.querySelector(`[data-person-card="${slug}"]`);
    if (!person) { if (old) old.remove(); return; }
    if (!old) { this._renderShell(); return; }
    const wrap = document.createElement("div");
    wrap.innerHTML = this._renderPersonCard(person);
    const next = wrap.firstElementChild;
    if (next) old.replaceWith(next);
  }

  async _loadCalendarEvents() {
    if (!this._state || !this._state.global) return;
    const ids = [this._state.global.calendar_entity_id, this._state.global.holiday_calendar_entity_id].filter(Boolean);
    if (!ids.length) { this._calendarEvents = {}; return; }
    const start = new Date(); start.setHours(0,0,0,0);
    const end = new Date(start); end.setDate(end.getDate() + 14);
    const map = {};
    for (const id of ids) {
      try {
        const events = await this._hass.callApi(
          "GET", `calendars/${id}?start=${start.toISOString()}&end=${end.toISOString()}`
        );
        for (const evt of (events || [])) {
          const raw = evt.start?.dateTime || evt.start?.date || "";
          if (!raw) continue;
          let key;
          if (raw.length <= 10) {
            key = raw.substring(0, 10); // all-day
          } else {
            const d = new Date(raw);
            key = isNaN(d.getTime()) ? raw.substring(0, 10) : localDateKey(d);
          }
          (map[key] = map[key] || []).push(evt);
        }
      } catch (_e) { /* ignore */ }
    }
    this._calendarEvents = map;
  }

  _toast(message, isError = false) {
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.textContent = message;
    this.appendChild(el);
    requestAnimationFrame(() => el.classList.add("show"));
    setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 200); }, 2500);
  }

  // ---------- Rendering ------------------------------------------------

  _renderShell() {
    if (!this._loaded) {
      this.innerHTML = `<style>${STYLES}</style><div class="empty">Loading Wake Planner…</div>`;
      return;
    }
    const persons = this._state?.persons || [];
    const tabs = ["today", "calendar", "people", "settings"];
    const labels = { today: "Today", calendar: "14 days", people: "People & rules", settings: "Settings" };

    let body = "";
    if (persons.length === 0 && this._tab !== "settings" && this._tab !== "people") {
      body = `<div class="card empty"><h2>No persons yet</h2><p class="muted">Add the first person under <b>People & rules</b>.</p><button class="btn primary" data-tab="people">Open People & rules</button></div>`;
    } else if (this._tab === "today") {
      body = `<div class="grid">${persons.map(p => this._renderToday(p)).join("")}</div>`;
    } else if (this._tab === "calendar") {
      body = this._renderCalendar(persons);
    } else if (this._tab === "people") {
      body = this._renderPeople(persons);
    } else if (this._tab === "settings") {
      body = this._renderSettings();
    }

    this.innerHTML = `
      <style>${STYLES}</style>
      <header>
        <h1>Wake Planner</h1>
        <span class="muted">${persons.length} ${persons.length === 1 ? "person" : "people"}</span>
      </header>
      <div class="tabs">
        ${tabs.map(t => `<button class="tab ${this._tab === t ? "active" : ""}" data-tab="${t}">${labels[t]}</button>`).join("")}
      </div>
      ${body}
    `;
  }

  _renderToday(person) {
    const dec = person.decision || {};
    const nextWake = person.next_wake ? new Date(person.next_wake) : null;
    const displayTime = nextWake ? nextWake.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
    const dayLabel = nextWake ? nextWake.toLocaleDateString([], { weekday: "long", day: "numeric", month: "short" }) : "";
    const decidedBy = dec.decided_by || "";
    let badgeClass = `b-${dec.state || "inactive"}`;
    if (decidedBy === "calendar") badgeClass = "b-calendar";
    const overrideInfo = person.override_time
      ? `<div class="muted">Override active: ${person.override_time}${person.override_until ? ` until ${person.override_until}` : ""}</div>`
      : "";
    const skipInfo = person.skip_next ? `<div class="muted">⚠ Next wake will be skipped</div>` : "";
    const skipClass = person.skip_next ? "btn state-skip" : "btn";
    const overrideClass = person.override_time ? "btn state-override" : "btn";
    const skipLabel = person.skip_next ? "✓ Skipping next" : "Skip next";
    return `<ha-card data-today-card="${person.slug}">
      <div class="row">
        <h2>${escapeHtml(person.name)}</h2>
        <span class="space"></span>
        <span class="badge ${badgeClass}">${dec.state || "inactive"}</span>
      </div>
      <div class="time">${displayTime}</div>
      <div class="muted">${dayLabel}</div>
      <div class="reason">${escapeHtml(dec.reason || "")}</div>
      ${overrideInfo}${skipInfo}
      <div class="row" style="margin-top:14px">
        <button class="${skipClass}" data-action="skip" data-person="${person.slug}">${skipLabel}</button>
        <button class="${overrideClass}" data-action="override" data-person="${person.slug}">${person.override_time ? `✓ Override ${person.override_time}` : "Override…"}</button>
        ${person.override_time || person.skip_next ? `<button class="btn" data-action="clear-override" data-person="${person.slug}">Clear</button>` : ""}
      </div>
    </ha-card>`;
  }

  _renderCalendar(persons) {
    const today = new Date(); today.setHours(0,0,0,0);
    const dayHeaders = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
    // Align grid to Monday
    const firstDow = (today.getDay() + 6) % 7;
    const cells = [];
    for (let i = 0; i < firstDow; i++) cells.push(`<div class="cal-day" style="opacity:.3"></div>`);
    const schedule = this._schedule || {};
    for (let i = 0; i < 14; i++) {
      const d = new Date(today); d.setDate(d.getDate() + i);
      const key = localDateKey(d);
      const isToday = i === 0;
      const isWeekend = d.getDay() === 0 || d.getDay() === 6;
      const events = this._calendarEvents[key] || [];
      const dayInfo = schedule[key];
      const holidayLabel = dayInfo?.holiday_name && dayInfo.holiday_name !== "Weekend"
        ? `<div class="cal-evt" style="color:var(--warning-color,#ef6c00)">🎉 ${escapeHtml(dayInfo.holiday_name)}</div>`
        : "";

      const wakes = persons.map(p => {
        const dec = (dayInfo?.persons || {})[p.slug];
        const fromCalendar = dec?.decided_by === "calendar";
        const indicator = fromCalendar ? " 📅" : "";
        if (!dec || !dec.wake_time) {
          const label = dec?.state === "holiday" ? "Feiertag" : (dec?.state === "skipped" ? "skip" : "—");
          return `<div class="cal-wake skip">${escapeHtml(p.name)}: ${label}</div>`;
        }
        return `<div class="cal-wake">${escapeHtml(p.name)}: ${dec.wake_time}${indicator}</div>`;
      }).join("");

      const otherEvts = events
        .filter(e => !/wake:/i.test(e.summary || ""))
        .slice(0, 3)
        .map(e => {
          const t = eventTimeLabel(e);
          return `<div class="cal-evt">• ${t ? `<b>${t}</b> ` : ""}${escapeHtml(e.summary || "")}</div>`;
        })
        .join("");

      cells.push(`<div class="cal-day${isToday ? " today" : ""}${isWeekend ? " weekend" : ""}">
        <div class="cal-date">${d.getDate()}.${d.getMonth() + 1}.</div>
        ${holidayLabel}${wakes}${otherEvts}
      </div>`);
    }
    return `<ha-card>
      <h2>Next 14 days</h2>
      <p class="muted">Today's wake times come from the rule engine; future days show wake events written to the calendar (if enabled).</p>
      <div class="cal-scroll">
        <div class="cal-grid" style="margin-bottom:6px">${dayHeaders.map(d => `<div class="muted" style="text-align:center;font-size:11px;font-weight:600;padding:4px">${d}</div>`).join("")}</div>
        <div class="cal-grid">${cells.join("")}</div>
      </div>
    </ha-card>`;
  }

  _renderPeople(persons) {
    const list = persons.length
      ? persons.map(p => this._renderPersonCard(p)).join("")
      : `<div class="card empty"><p>No persons yet. Add the first one to get started.</p></div>`;
    const personOptions = this._personEntityOptions();
    return `${list}
      <ha-card>
        <h2>Add person</h2>
        <div class="row" style="margin-top:8px;align-items:flex-end">
          <label class="field" style="flex:1;min-width:160px"><span class="label">Name</span>
            <input type="text" id="add-name" placeholder="e.g. Benni">
          </label>
          <label class="field" style="flex:1;min-width:200px"><span class="label">Link to HA person (optional)</span>
            <select id="add-person-entity">
              <option value="">— none —</option>
              ${personOptions.map(o => `<option value="${o.id}">${escapeHtml(o.name)} (${o.id})</option>`).join("")}
            </select>
          </label>
          <button class="btn primary" data-action="add-person">Add</button>
        </div>
        <p class="muted" style="margin-top:8px">A default weekday-mornings rule (Mon–Fri 07:00) is created automatically. The HA person link lets future features (presence-based skip etc.) hook in.</p>
      </ha-card>`;
  }

  _personEntityOptions() {
    if (!this._hass) return [];
    return Object.entries(this._hass.states)
      .filter(([id]) => id.startsWith("person."))
      .map(([id, s]) => ({ id, name: s.attributes?.friendly_name || id }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  _renderPersonCard(person) {
    const rulesHtml = (person.rules || []).length
      ? (person.rules || []).map((r, idx) => this._renderRule(person.slug, r, idx)).join("")
      : `<p class="muted">No rules yet — without a rule this person will be inactive.</p>`;
    const linkLabel = person.person_entity_id
      ? `linked to <code>${escapeHtml(person.person_entity_id)}</code>`
      : `<span style="opacity:.6">no HA person linked</span>`;
    return `<ha-card data-person-card="${person.slug}">
      <div class="row">
        <h2>${escapeHtml(person.name)}</h2>
        <span class="muted">slug: ${person.slug} · ${linkLabel}</span>
        <span class="space"></span>
        <button class="btn" data-action="edit-person" data-person="${person.slug}">Edit</button>
        <button class="btn danger" data-action="remove-person" data-person="${person.slug}">Delete</button>
      </div>
      <p class="muted" style="margin:8px 0 12px">Rules are evaluated in priority order (lowest number first). The first matching rule wins.</p>
      <div data-rules-list="${person.slug}">${rulesHtml}</div>
      <div class="row" style="margin-top:10px">
        <button class="btn primary" data-action="add-rule" data-person="${person.slug}">+ Add rule</button>
        <span class="space"></span>
        <label class="field" style="flex-direction:row;align-items:center;gap:8px">
          <span class="label">Wake window (min)</span>
          <input type="number" min="1" max="120" value="${person.wake_window_minutes || 5}" data-window-for="${person.slug}" style="width:80px">
        </label>
        <button class="btn" data-action="save-window" data-person="${person.slug}">Save</button>
      </div>
    </ha-card>`;
  }

  _renderRule(slug, rule, index) {
    const wd = new Set(rule.weekdays || []);
    const weekdaysHtml = WEEKDAYS.map(d => `
      <label class="${wd.has(d.idx) ? "on" : ""}" title="${d.long}">
        <input type="checkbox" data-rule-wd="${slug}|${rule.id}|${d.idx}" ${wd.has(d.idx) ? "checked" : ""}>
        ${d.short}
      </label>`).join("");

    const actionWake = rule.action === "wake" || !rule.action;
    return `<div class="rule-card${rule.enabled ? "" : " disabled"}">
      <div class="rule-head">
        <input type="text" value="${escapeHtml(rule.name || "Rule")}" data-rule-field="${slug}|${rule.id}|name" style="flex:1;font-weight:600">
        <span class="rule-prio">prio ${rule.priority}</span>
        <label class="row" style="gap:4px;font-size:12px">
          <input type="checkbox" ${rule.enabled ? "checked" : ""} data-rule-field="${slug}|${rule.id}|enabled">
          on
        </label>
        <button class="icon-btn" title="Delete rule" data-action="delete-rule" data-person="${slug}" data-rule="${rule.id}">🗑</button>
      </div>
      <div class="row" style="gap:14px">
        <label class="field"><span class="label">Action</span>
          <select data-rule-field="${slug}|${rule.id}|action">
            <option value="wake" ${actionWake ? "selected" : ""}>Wake at</option>
            <option value="skip" ${rule.action === "skip" ? "selected" : ""}>Skip (no wake)</option>
          </select>
        </label>
        <label class="field" style="${actionWake ? "" : "visibility:hidden"}"><span class="label">Time</span>
          <input type="time" value="${rule.wake_time || "07:00"}" data-rule-field="${slug}|${rule.id}|wake_time">
        </label>
        <label class="field"><span class="label">Priority</span>
          <input type="number" value="${rule.priority}" data-rule-field="${slug}|${rule.id}|priority" style="width:80px">
        </label>
      </div>
      <div style="margin:10px 0 6px"><span class="label" style="font-size:11px;opacity:.7;font-weight:600;text-transform:uppercase;letter-spacing:.04em">Weekdays (any match)</span></div>
      <div class="weekday-toggle">${weekdaysHtml}</div>

      <div class="row" style="gap:14px;margin-top:12px">
        <label class="field"><span class="label">Holiday</span>
          <select data-rule-field="${slug}|${rule.id}|on_holiday">
            <option value="" ${rule.on_holiday === null || rule.on_holiday === undefined ? "selected" : ""}>Ignore (any day)</option>
            <option value="true" ${rule.on_holiday === true ? "selected" : ""}>Only on holidays</option>
            <option value="false" ${rule.on_holiday === false ? "selected" : ""}>Only on non-holidays</option>
          </select>
        </label>
      </div>

      <details style="margin-top:12px">
        <summary style="cursor:pointer;font-size:12px;opacity:.75">Advanced conditions (date range, alternating weeks, shift cycle, one-off dates)</summary>
        <div class="row" style="gap:14px;margin-top:10px">
          <label class="field"><span class="label">From date</span>
            <input type="date" value="${rule.date_from || ""}" data-rule-field="${slug}|${rule.id}|date_from">
          </label>
          <label class="field"><span class="label">To date</span>
            <input type="date" value="${rule.date_to || ""}" data-rule-field="${slug}|${rule.id}|date_to">
          </label>
        </div>
        <div class="row" style="gap:14px;margin-top:10px">
          <label class="field"><span class="label">Every N weeks</span>
            <input type="number" min="1" value="${rule.week_interval || ""}" placeholder="2" data-rule-field="${slug}|${rule.id}|week_interval" style="width:90px">
          </label>
          <label class="field"><span class="label">Week anchor (a Monday)</span>
            <input type="date" value="${rule.week_anchor || ""}" data-rule-field="${slug}|${rule.id}|week_anchor">
          </label>
        </div>
        <div class="row" style="gap:14px;margin-top:10px">
          <label class="field" style="flex:1;min-width:220px"><span class="label">Specific dates (YYYY-MM-DD, comma-separated)</span>
            <input type="text" value="${(rule.specific_dates || []).join(", ")}" placeholder="2026-06-15, 2026-12-24" data-rule-field="${slug}|${rule.id}|specific_dates">
          </label>
        </div>
        <div class="row" style="gap:14px;margin-top:10px">
          <label class="field"><span class="label">Cycle anchor</span>
            <input type="date" value="${rule.cycle_anchor || ""}" data-rule-field="${slug}|${rule.id}|cycle_anchor">
          </label>
          <label class="field"><span class="label">Cycle length (days)</span>
            <input type="number" min="1" value="${rule.cycle_length || ""}" data-rule-field="${slug}|${rule.id}|cycle_length" style="width:120px">
          </label>
          <label class="field"><span class="label">Slot start (day)</span>
            <input type="number" min="0" value="${rule.cycle_slot_start ?? ""}" data-rule-field="${slug}|${rule.id}|cycle_slot_start" style="width:110px">
          </label>
          <label class="field"><span class="label">Slot length (days)</span>
            <input type="number" min="1" value="${rule.cycle_slot_length || ""}" data-rule-field="${slug}|${rule.id}|cycle_slot_length" style="width:120px">
          </label>
        </div>
      </details>

      <div class="row" style="margin-top:12px">
        <span class="space"></span>
        <button class="btn primary" data-action="save-rule" data-person="${slug}" data-rule="${rule.id}">Save rule</button>
      </div>
    </div>`;
  }

  _renderSettings() {
    const g = this._state.global || {};
    const calOptions = this._calendarEntityOptions();
    return `<ha-card>
      <h2>Global settings</h2>
      <section class="settings-section">
        <h3>Calendars</h3>
        <p class="muted">Wake events with titles like <code>wake: 06:30</code> override that day's rule. All-day events with titles matching <code>no-wake</code>/<code>schlaf aus</code> skip the day.</p>
        <div class="row" style="gap:14px;margin-top:8px">
          <label class="field" style="flex:1;min-width:200px"><span class="label">Wake calendar (read & optional write)</span>
            <select data-global-field="calendar_entity_id">
              <option value="">— none —</option>
              ${calOptions.map(o => `<option value="${o.id}" ${o.id === g.calendar_entity_id ? "selected" : ""}>${escapeHtml(o.name)}</option>`).join("")}
            </select>
          </label>
          <label class="field" style="flex:1;min-width:200px"><span class="label">Holiday calendar (all-day events)</span>
            <select data-global-field="holiday_calendar_entity_id">
              <option value="">— none —</option>
              ${calOptions.map(o => `<option value="${o.id}" ${o.id === g.holiday_calendar_entity_id ? "selected" : ""}>${escapeHtml(o.name)}</option>`).join("")}
            </select>
          </label>
        </div>
        <p class="muted" style="margin-top:8px">Wake Planner only <b>reads</b> from the wake calendar — no events are written back. To change a wake time on a specific day, use the Override button on the Today tab or add a calendar event with a title like <code>wake: 06:30</code>.</p>
      </section>
      <section class="settings-section">
        <h3>Weekends &amp; holidays</h3>
        <div class="row" style="gap:14px;margin-top:8px">
          <label class="field"><span class="label">Behaviour</span>
            <select data-global-field="holiday_behavior">
              <option value="skip" ${g.holiday_behavior === "skip" ? "selected" : ""}>Skip wake (incl. weekends)</option>
              <option value="weekend_profile" ${g.holiday_behavior === "weekend_profile" ? "selected" : ""}>Treat as weekend (use Sat-rule)</option>
            </select>
          </label>
          <label class="field" style="flex:1;min-width:220px"><span class="label">Manual holiday dates / ranges</span>
            <input type="text" value="${escapeHtml(g.manual_holiday_dates || "")}" data-global-field="manual_holiday_dates" placeholder="2026-12-25, 12-26, 2026-07-01..2026-07-14">
          </label>
        </div>
        <p class="muted" style="margin-top:8px">Formats: <code>YYYY-MM-DD</code>, <code>MM-DD</code> (yearly), ranges with <code>..</code>, comma separated.</p>
      </section>
      <div class="row" style="margin-top:14px">
        <span class="space"></span>
        <button class="btn primary" data-action="save-global">Save global settings</button>
      </div>
    </ha-card>`;
  }

  _calendarEntityOptions() {
    if (!this._hass) return [];
    return Object.entries(this._hass.states)
      .filter(([id]) => id.startsWith("calendar."))
      .map(([id, s]) => ({ id, name: s.attributes?.friendly_name || id }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  // ---------- Actions (handled via delegated click) -------------------

  async _handleAction(el) {
    const action = el.dataset.action;
    const slug = el.dataset.person;
    if (action === "skip") {
      const ok = await this._ws("wake_planner/skip_next", { person_id: slug });
      if (ok) { this._updateTodayCard(slug); this._flashSuccess(el); this._toast("Next wake skipped"); }
    }
    else if (action === "clear-override") {
      const ok = await this._ws("wake_planner/clear_override", { person_id: slug });
      if (ok) { this._updateTodayCard(slug); this._flashSuccess(el); this._toast("Cleared"); }
    }
    else if (action === "override") this._openOverrideDialog(slug, el);
    else if (action === "add-person") {
      const name = this.querySelector("#add-name")?.value?.trim();
      if (!name) return this._toast("Enter a name", true);
      const personEntity = this.querySelector("#add-person-entity")?.value || null;
      const ok = await this._ws("wake_planner/add_person", { name, person_entity_id: personEntity });
      if (ok) { this._flashSuccess(el); this._renderShell(); }
    }
    else if (action === "remove-person") {
      const person = this._state.persons.find(p => p.slug === slug);
      if (!confirm(`Delete ${person?.name || slug}? Rules and runtime state will be lost.`)) return;
      const ok = await this._ws("wake_planner/remove_person", { person_id: slug });
      if (ok) this._renderShell();
    }
    else if (action === "edit-person") this._openEditPersonDialog(slug);
    else if (action === "add-rule") await this._addRule(slug, el);
    else if (action === "delete-rule") await this._deleteRule(slug, el.dataset.rule);
    else if (action === "save-rule") await this._saveRule(slug, el.dataset.rule, el);
    else if (action === "save-window") await this._saveWindow(slug, el);
    else if (action === "save-global") await this._saveGlobal(el);
  }

  _collectRuleFields(slug, ruleId) {
    const out = {};
    this.querySelectorAll(`[data-rule-field^="${slug}|${ruleId}|"]`).forEach(input => {
      const field = input.dataset.ruleField.split("|")[2];
      if (input.type === "checkbox") out[field] = input.checked;
      else if (input.type === "number") {
        const v = input.value.trim();
        out[field] = v === "" ? null : Number(v);
      } else {
        out[field] = input.value;
      }
    });
    const weekdays = [];
    this.querySelectorAll(`[data-rule-wd^="${slug}|${ruleId}|"]`).forEach(input => {
      if (input.checked) weekdays.push(Number(input.dataset.ruleWd.split("|")[2]));
    });
    out.weekdays = weekdays.length ? weekdays : null;
    // Normalise
    if (out.specific_dates && typeof out.specific_dates === "string") {
      const parts = out.specific_dates.split(/[,;\s]+/).map(s => s.trim()).filter(Boolean);
      out.specific_dates = parts.length ? parts : null;
    }
    for (const k of ["date_from", "date_to", "week_anchor", "cycle_anchor"]) {
      if (out[k] === "") out[k] = null;
    }
    if ("on_holiday" in out) {
      if (out.on_holiday === "" || out.on_holiday === null) out.on_holiday = null;
      else if (out.on_holiday === "true" || out.on_holiday === true) out.on_holiday = true;
      else if (out.on_holiday === "false" || out.on_holiday === false) out.on_holiday = false;
    }
    if (out.action === "skip") out.wake_time = null;
    return out;
  }

  async _saveRule(slug, ruleId, btn) {
    const person = this._state.persons.find(p => p.slug === slug);
    if (!person) return;
    const updated = this._collectRuleFields(slug, ruleId);
    const rules = person.rules.map(r => r.id === ruleId ? { ...r, ...updated, id: r.id } : r);
    const ok = await this._ws("wake_planner/set_rules", { person_id: slug, rules });
    if (ok) { this._flashSuccess(btn); this._toast("Rule saved"); this._updateTodayCard(slug); }
  }

  async _addRule(slug, btn) {
    const person = this._state.persons.find(p => p.slug === slug);
    if (!person) return;
    const newRule = {
      id: cryptoRandomId(),
      name: "New rule",
      priority: 50,
      enabled: true,
      weekdays: [0,1,2,3,4],
      action: "wake",
      wake_time: "07:00",
    };
    const rules = [...person.rules, newRule];
    const ok = await this._ws("wake_planner/set_rules", { person_id: slug, rules });
    if (ok) { this._flashSuccess(btn); this._updatePersonCard(slug); this._updateTodayCard(slug); }
  }

  async _deleteRule(slug, ruleId) {
    const person = this._state.persons.find(p => p.slug === slug);
    if (!person) return;
    if (!confirm("Delete this rule?")) return;
    const ok = await this._ws("wake_planner/set_rules", { person_id: slug, rules: person.rules.filter(r => r.id !== ruleId) });
    if (ok) { this._updatePersonCard(slug); this._updateTodayCard(slug); this._toast("Rule deleted"); }
  }

  async _saveWindow(slug, btn) {
    const el = this.querySelector(`[data-window-for="${slug}"]`);
    const minutes = Math.max(1, Math.min(120, parseInt(el?.value || "5", 10)));
    const ok = await this._ws("wake_planner/update_person", { person_id: slug, wake_window_minutes: minutes });
    if (ok) { this._flashSuccess(btn); this._toast("Saved"); }
  }

  async _saveGlobal(btn) {
    const payload = {};
    this.querySelectorAll("[data-global-field]").forEach(el => {
      const key = el.dataset.globalField;
      if (el.type === "checkbox") payload[key] = el.checked;
      else payload[key] = el.value;
    });
    const ok = await this._ws("wake_planner/set_global", payload);
    if (ok) { this._flashSuccess(btn); this._toast("Settings saved"); }
  }

  _openOverrideDialog(slug, sourceBtn) {
    const person = this._state.persons.find(p => p.slug === slug);
    const initialTime = person?.override_time || person?.decision?.wake_time || "07:00";
    const initialUntil = person?.override_until || "";
    this._openModal(`Override for ${escapeHtml(person?.name || slug)}`, `
      <label class="field"><span class="label">Wake time</span>
        <input type="time" id="ov-time" value="${initialTime}">
      </label>
      <label class="field" style="margin-top:12px"><span class="label">Until (optional)</span>
        <input type="date" id="ov-until" value="${initialUntil}">
      </label>
      <p class="muted" style="margin-top:8px">Leave empty for one-day override; the override applies to every day up to and including this date.</p>
    `, async (modal) => {
      const wake = modal.querySelector("#ov-time").value;
      const until = modal.querySelector("#ov-until").value || null;
      const ok = await this._ws("wake_planner/set_override", { person_id: slug, wake_time: wake, until });
      if (ok) { this._updateTodayCard(slug); this._flashSuccess(sourceBtn); this._toast("Override set"); }
    });
  }

  _openEditPersonDialog(slug) {
    const person = this._state.persons.find(p => p.slug === slug);
    const opts = this._personEntityOptions();
    const currentEntity = person?.person_entity_id || "";
    this._openModal(`Edit ${escapeHtml(person?.name || slug)}`, `
      <label class="field"><span class="label">Name</span>
        <input type="text" id="ep-name" value="${escapeHtml(person?.name || "")}">
      </label>
      <label class="field" style="margin-top:12px"><span class="label">Linked HA person</span>
        <select id="ep-entity">
          <option value="">— none —</option>
          ${opts.map(o => `<option value="${o.id}" ${o.id === currentEntity ? "selected" : ""}>${escapeHtml(o.name)} (${o.id})</option>`).join("")}
        </select>
      </label>
      <p class="muted" style="margin-top:8px">Linking is optional and currently informational — the slug stays the same when you rename.</p>
    `, async (modal) => {
      const name = modal.querySelector("#ep-name").value.trim();
      const entity = modal.querySelector("#ep-entity").value || null;
      if (!name) return;
      const ok = await this._ws("wake_planner/update_person", { person_id: slug, name, person_entity_id: entity });
      if (ok) { this._updatePersonCard(slug); this._updateTodayCard(slug); this._toast("Saved"); }
    });
  }

  _openModal(title, bodyHtml, onConfirm) {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal" role="dialog">
        <h2>${title}</h2>
        ${bodyHtml}
        <div class="modal-actions">
          <button class="btn" data-modal-cancel>Cancel</button>
          <button class="btn primary" data-modal-confirm>OK</button>
        </div>
      </div>`;
    this.appendChild(backdrop);
    backdrop.addEventListener("click", e => { if (e.target === backdrop) backdrop.remove(); });
    backdrop.querySelector("[data-modal-cancel]").addEventListener("click", () => backdrop.remove());
    backdrop.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
      try { await onConfirm(backdrop); } finally { backdrop.remove(); }
    });
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function localDateKey(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function eventTimeLabel(evt) {
  const raw = evt?.start?.dateTime || evt?.start?.date_time || evt?.start;
  if (!raw || typeof raw !== "string" || raw.length <= 10) return ""; // all-day
  try {
    const d = new Date(raw);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

function cryptoRandomId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return "r-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

customElements.define("wake-planner-panel", WakePlannerPanel);
