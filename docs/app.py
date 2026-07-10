"""
Betaflight Config Editor — app.py
PyScript application logic: parse, render, export.
"""

import json
import re
import asyncio
from pyscript import document, when
from pyscript.ffi import create_proxy
import js

# ── Global State ──────────────────────────────────────────────────────────────
PARAMS = []           # ordered list of param dicts from params.json
parsed = None         # result of parse_cli()
cur_pid  = 0          # currently selected PID profile index
cur_rate = 0          # currently selected rate profile index


# ── Utility ───────────────────────────────────────────────────────────────────
def esc(text):
    """HTML-escape a value for safe injection into innerHTML."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))


def get_val(key, meta):
    """Fetch the current param value from parsed state."""
    if parsed is None:
        return ""
    if meta.get("profile_scoped"):
        return parsed["profiles"].get(cur_pid, {}).get(key, "")
    if meta.get("rate_scoped"):
        return parsed["rateprofiles"].get(cur_rate, {}).get(key, "")
    # Global first, fall back to first profile (some set commands land there)
    v = parsed["global_params"].get(key, "")
    if v == "" and parsed["profiles"]:
        first = min(parsed["profiles"])
        v = parsed["profiles"][first].get(key, "")
    return v


# ── CLI Parser ────────────────────────────────────────────────────────────────
def parse_cli(text):
    result = {
        "header_lines":    [],
        "global_params":   {},
        "profiles":        {},
        "rateprofiles":    {},
        "mode_ranges":     [],
        "adjranges":       [],
        "other_lines":     [],
        "bf_version":      None,
        "profile_count":   1,
        "rateprofile_count": 1,
    }

    in_header   = True
    cur_profile  = None
    cur_ratep    = None

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        # ── Header block (comments before first command) ──
        if in_header:
            if stripped.startswith("#") or stripped == "":
                result["header_lines"].append(line)
                # Extract BF version from "# Betaflight / TARGET / X.Y.Z ..."
                m = re.search(r'Betaflight\s*/\s*\S+\s*/\s*(\d+\.\d+\.\d+)', stripped)
                if m:
                    result["bf_version"] = m.group(1)
                continue
            else:
                in_header = False

        if not stripped or stripped == "save":
            continue

        # ── Profile / rateprofile headers ──
        if re.match(r'^profile\s+\d+$', stripped):
            cur_profile = int(stripped.split()[1])
            cur_ratep   = None
            result["profiles"].setdefault(cur_profile, {})
            result["profile_count"] = max(result["profile_count"], cur_profile + 1)
            continue

        if re.match(r'^rateprofile\s+\d+$', stripped):
            cur_ratep   = int(stripped.split()[1])
            cur_profile = None
            result["rateprofiles"].setdefault(cur_ratep, {})
            result["rateprofile_count"] = max(result["rateprofile_count"], cur_ratep + 1)
            continue

        # ── set param = value ──
        if stripped.startswith("set ") and " = " in stripped:
            _, rest = stripped.split(" ", 1)
            key, value = rest.split(" = ", 1)
            key = key.strip(); value = value.strip()
            if cur_ratep is not None:
                result["rateprofiles"][cur_ratep][key] = value
            elif cur_profile is not None:
                result["profiles"][cur_profile][key] = value
            else:
                result["global_params"][key] = value
            continue

        # ── Structured passthrough lines ──
        if stripped.startswith("mode_range "):
            result["mode_ranges"].append(stripped)
            continue
        if stripped.startswith("adjrange "):
            result["adjranges"].append(stripped)
            continue

        # ── Everything else: passthrough verbatim ──
        result["other_lines"].append(line)

    return result


# ── Field HTML Builder ────────────────────────────────────────────────────────
def build_field(key, meta, value):
    ftype     = meta.get("type", "string")
    label     = esc(meta.get("label", key))
    desc      = esc(meta.get("description", ""))
    hw        = meta.get("hardware_specific", False)
    is_ro     = ftype == "readonly" or hw
    unit      = esc(meta.get("unit", ""))
    note      = esc(meta.get("note", ""))
    val_safe  = esc(value)

    css = "field-group hw-locked" if hw else "field-group"

    tip_html = (f'<span class="tooltip-icon" data-tip="{desc}">?</span>'
                if desc else "")

    absent_hidden = ""
    input_html = ""

    if is_ro:
        hw_badge = ('<span class="hw-badge">🔒 Hardware-specific — do not copy between builds</span>'
                    if hw else "")
        note_html = f'<span class="field-note">{note}</span>' if note else ""
        input_html = (f'<input type="text" id="field-{key}" value="{val_safe}" '
                      f'readonly>'
                      f'{hw_badge}{note_html}')

    elif value == "" and not is_ro:
        # Param not present in imported config
        absent_hidden = f'<input type="hidden" id="field-{key}" value="" data-absent="true">'
        input_html = (absent_hidden +
                      '<span class="field-absent">Not present in imported config</span>')

    elif ftype == "bool":
        checked = "checked" if str(value).upper() in ("ON", "TRUE", "1") else ""
        input_html = (f'<div class="toggle-wrap">'
                      f'<label class="toggle-label">'
                      f'<input type="checkbox" id="field-{key}" {checked}>'
                      f'<span class="toggle-slider"></span></label>'
                      f'<span class="toggle-state-label" id="field-{key}-lbl">'
                      f'{"ON" if checked else "OFF"}</span>'
                      f'</div>')

    elif ftype == "enum":
        opts = meta.get("options", [])
        options_html = ""
        matched = False
        for opt in opts:
            # Support "0 (500Hz)" style — value key is the part before the space
            opt_key = opt.split(" ")[0] if " " in opt else opt
            sel = "selected" if (opt_key == value or opt == value) else ""
            if sel:
                matched = True
            options_html += f'<option value="{esc(opt_key)}" {sel}>{esc(opt)}</option>'
        if not matched and value:
            options_html += (f'<option value="{val_safe}" selected>'
                             f'{val_safe} (from config)</option>')
        input_html = (f'<select id="field-{key}">{options_html}</select>')

    elif ftype in ("int", "float"):
        rng = meta.get("range", [0, 10000])
        unit_span = f'<span class="unit-label">{unit}</span>' if unit else ""
        input_html = (f'<div class="field-number-wrap">'
                      f'<input type="number" id="field-{key}" value="{val_safe}" '
                      f'min="{rng[0]}" max="{rng[1]}">'
                      f'{unit_span}</div>')

    else:  # string
        input_html = f'<input type="text" id="field-{key}" value="{val_safe}">'

    return (f'<div class="{css}" id="fg-{key}">'
            f'<div class="field-label-row">'
            f'<span class="field-label">{label}</span>{tip_html}</div>'
            f'{input_html}</div>')


# ── Form Population ───────────────────────────────────────────────────────────
def render_tab(tab_name, container_id, pid_profile=None, rate_profile=None):
    el = document.getElementById(container_id)
    if not el:
        return

    current_section = None
    parts = []

    for meta in PARAMS:
        if meta.get("tab") != tab_name:
            continue

        key   = meta["key"]
        sec   = meta.get("section", "")

        if sec != current_section:
            current_section = sec
            parts.append(f'<div class="section-header">{esc(sec)}</div>')

        if meta.get("profile_scoped"):
            value = (parsed["profiles"].get(pid_profile, {}).get(key, "")
                     if parsed else "")
        elif meta.get("rate_scoped"):
            value = (parsed["rateprofiles"].get(rate_profile, {}).get(key, "")
                     if parsed else "")
        else:
            value = get_val(key, meta)

        parts.append(build_field(key, meta, value))

    el.innerHTML = "".join(parts)

    # Wire up toggle labels after injection
    for meta in PARAMS:
        if meta.get("tab") == tab_name and meta.get("type") == "bool":
            _attach_toggle_label(meta["key"])


def _attach_toggle_label(key):
    cb  = document.getElementById(f"field-{key}")
    lbl = document.getElementById(f"field-{key}-lbl")
    if not (cb and lbl):
        return
    def on_change(e):
        lbl.textContent = "ON" if e.target.checked else "OFF"
    cb.addEventListener("change", create_proxy(on_change))


def render_all():
    for tab in ("configuration", "power_battery", "filtering", "receiver", "vtx"):
        render_tab(tab, f"fields-{tab}")
    render_tab("pid_tuning", "fields-pid_tuning", pid_profile=cur_pid)
    render_tab("rates",      "fields-rates",      rate_profile=cur_rate)


# ── Info Bar ──────────────────────────────────────────────────────────────────
def update_info_bar():
    version = parsed.get("bf_version") or "—"
    craft   = parsed["global_params"].get("craft_name", "")
    if not craft:
        for p in parsed["profiles"].values():
            craft = p.get("craft_name", "")
            if craft:
                break
    craft = craft or "—"
    pc  = parsed["profile_count"]
    rpc = parsed["rateprofile_count"]

    def set_badge(bid, val):
        el = document.getElementById(bid)
        if el:
            el.innerHTML = val

    set_badge("info-version",      f'BF <span>{esc(version)}</span>')
    set_badge("info-craft",        f'Craft: <span>{esc(craft)}</span>')
    set_badge("info-pid-profiles", f'PID Profiles: <span>{pc}</span>')
    set_badge("info-rate-profiles",f'Rate Profiles: <span>{rpc}</span>')

    # Populate profile selects
    for sel_id, count in (("pid-profile-select", pc),
                          ("rate-profile-select", rpc)):
        sel = document.getElementById(sel_id)
        if sel:
            sel.innerHTML = "".join(
                f'<option value="{i}">Profile {i}</option>'
                for i in range(count)
            )


def prepopulate_paste_areas():
    mode_el = document.getElementById("mode-range-paste")
    adj_el  = document.getElementById("adjrange-paste")
    if mode_el:
        mode_el.value = "\n".join(parsed.get("mode_ranges", []))
    if adj_el:
        adj_el.value = "\n".join(parsed.get("adjranges", []))


# ── Load Config ───────────────────────────────────────────────────────────────
def process_cli_text(text):
    global parsed, cur_pid, cur_rate

    if not text.strip():
        show_error("Nothing to load. Upload a file or paste CLI text first.")
        return

    parsed   = parse_cli(text)
    cur_pid  = 0
    cur_rate = 0

    update_info_bar()
    render_all()
    prepopulate_paste_areas()

    # Set export filename
    craft = parsed["global_params"].get("craft_name", "")
    if not craft:
        for p in parsed["profiles"].values():
            craft = p.get("craft_name", "")
            if craft:
                break
    fn = (craft or "config").replace('"', "").replace(" ", "_")
    fname_el = document.getElementById("export-filename")
    if fname_el:
        fname_el.value = f"{fn}_edited.txt"

    # Show hidden sections
    for el_id in ("config-info", "editor-section", "export-section"):
        el = document.getElementById(el_id)
        if el:
            el.style.display = "block"

    hide_error()
    switch_tab("configuration")


def show_error(msg):
    el = document.getElementById("import-error")
    if el:
        el.textContent = msg
        el.style.display = "block"


def hide_error():
    el = document.getElementById("import-error")
    if el:
        el.style.display = "none"


# ── Event: File Upload ────────────────────────────────────────────────────────
async def _read_file(event):
    files = event.target.files
    if not files or files.length == 0:
        return
    f = files.item(0)
    fn_el = document.getElementById("file-name")
    if fn_el:
        fn_el.textContent = f.name
    text = await f.text()
    process_cli_text(text)


def _file_upload_handler(event):
    asyncio.ensure_future(_read_file(event))


# ── Event: Load Button ────────────────────────────────────────────────────────
def _load_btn_handler(event):
    paste = document.getElementById("paste-area")
    if paste and paste.value.strip():
        process_cli_text(paste.value)
    else:
        show_error("Please upload a .txt file or paste CLI text above.")


# ── Tab Switching ─────────────────────────────────────────────────────────────
def switch_tab(tab_name):
    tabs = ("configuration", "power_battery", "pid_tuning",
            "filtering", "receiver", "vtx", "modes", "adjustments")

    for t in tabs:
        panel = document.getElementById(f"tab-{t}")
        if panel:
            panel.classList.toggle("active", t == tab_name)

    btns = document.querySelectorAll(".tab-btn")
    for i in range(btns.length):
        btn = btns.item(i)
        btn.classList.toggle("active",
                             btn.getAttribute("data-tab") == tab_name)

    # Show profile selectors only on PID Tuning tab
    prof_row = document.getElementById("profile-selector-row")
    if prof_row:
        prof_row.style.display = "flex" if tab_name == "pid_tuning" else "none"


def _make_tab_handler(tab_name):
    def handler(event):
        switch_tab(tab_name)
    return create_proxy(handler)


# ── Profile Changes ───────────────────────────────────────────────────────────
def _pid_profile_handler(event):
    global cur_pid
    cur_pid = int(event.target.value)
    render_tab("pid_tuning", "fields-pid_tuning", pid_profile=cur_pid)


def _rate_profile_handler(event):
    global cur_rate
    cur_rate = int(event.target.value)
    render_tab("rates", "fields-rates", rate_profile=cur_rate)


# ── Export ────────────────────────────────────────────────────────────────────
def read_field(key, meta):
    """Read current form value for a param, or None if absent/skipped."""
    el = document.getElementById(f"field-{key}")
    if not el:
        return None
    if el.getAttribute("data-absent") == "true":
        return None

    ftype = meta.get("type", "string")
    if ftype == "readonly" or meta.get("hardware_specific"):
        return el.value  # preserve original

    if ftype == "bool":
        return "ON" if el.checked else "OFF"

    return el.value


def generate_export():
    if not parsed:
        return ""

    lines = []

    # ── Preserved header ──
    lines.extend(parsed["header_lines"])

    # ── Global set params ──
    global_out = dict(parsed["global_params"])
    for meta in PARAMS:
        key = meta["key"]
        if meta.get("profile_scoped") or meta.get("rate_scoped"):
            continue
        val = read_field(key, meta)
        if val is not None and val != "":
            global_out[key] = val
    for k, v in global_out.items():
        lines.append(f"set {k} = {v}")

    # ── Passthrough lines (vtxtable, beacon, serial, etc.) ──
    lines.extend(parsed["other_lines"])

    # ── PID profiles ──
    for p_num, p_params in sorted(parsed["profiles"].items()):
        lines.append("")
        lines.append(f"profile {p_num}")
        profile_out = dict(p_params)
        if p_num == cur_pid:
            for meta in PARAMS:
                if not meta.get("profile_scoped"):
                    continue
                val = read_field(meta["key"], meta)
                if val is not None and val != "":
                    profile_out[meta["key"]] = val
        for k, v in profile_out.items():
            lines.append(f"set {k} = {v}")

    # ── Rate profiles ──
    for r_num, r_params in sorted(parsed["rateprofiles"].items()):
        lines.append("")
        lines.append(f"rateprofile {r_num}")
        rp_out = dict(r_params)
        if r_num == cur_rate:
            for meta in PARAMS:
                if not meta.get("rate_scoped"):
                    continue
                val = read_field(meta["key"], meta)
                if val is not None and val != "":
                    rp_out[meta["key"]] = val
        for k, v in rp_out.items():
            lines.append(f"set {k} = {v}")

    lines.append("")

    # ── Mode ranges (override or preserve) ──
    mode_paste = document.getElementById("mode-range-paste")
    if mode_paste and mode_paste.value.strip():
        for ln in mode_paste.value.strip().split("\n"):
            ln = ln.strip()
            if ln.startswith("mode_range"):
                lines.append(ln)
    else:
        lines.extend(parsed["mode_ranges"])

    # ── Adjranges (override or preserve) ──
    adj_paste = document.getElementById("adjrange-paste")
    if adj_paste and adj_paste.value.strip():
        for ln in adj_paste.value.strip().split("\n"):
            ln = ln.strip()
            if ln.startswith("adjrange"):
                lines.append(ln)
    else:
        lines.extend(parsed["adjranges"])

    lines.append("")
    lines.append("save")
    return "\n".join(lines)


def _export_handler(event):
    cli_text = generate_export()
    if not cli_text:
        return
    fname_el = document.getElementById("export-filename")
    filename = (fname_el.value.strip() if fname_el else "") or "exported_config.txt"
    if not filename.endswith(".txt"):
        filename += ".txt"

    blob = js.Blob.new([cli_text], {"type": "text/plain"})
    url  = js.URL.createObjectURL(blob)
    a    = document.createElement("a")
    a.href     = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    js.URL.revokeObjectURL(url)


# ── Initialisation ────────────────────────────────────────────────────────────
def init():
    global PARAMS

    # Load params from the inline JSON block
    params_el = document.getElementById("params-data")
    if params_el:
        PARAMS = json.loads(params_el.textContent)

    # Wire events
    fu = document.getElementById("file-upload")
    if fu:
        fu.addEventListener("change", create_proxy(_file_upload_handler))

    lb = document.getElementById("load-btn")
    if lb:
        lb.addEventListener("click", create_proxy(_load_btn_handler))

    eb = document.getElementById("export-btn")
    if eb:
        eb.addEventListener("click", create_proxy(_export_handler))

    pp = document.getElementById("pid-profile-select")
    if pp:
        pp.addEventListener("change", create_proxy(_pid_profile_handler))

    rp = document.getElementById("rate-profile-select")
    if rp:
        rp.addEventListener("change", create_proxy(_rate_profile_handler))

    # Tab buttons
    btns = document.querySelectorAll(".tab-btn")
    for i in range(btns.length):
        btn = btns.item(i)
        tab = btn.getAttribute("data-tab")
        if tab:
            btn.addEventListener("click", _make_tab_handler(tab))

    # Hide loading overlay
    overlay = document.getElementById("loading-overlay")
    if overlay:
        overlay.style.display = "none"


init()
