# Betaflight Config Editor

A browser-based tool for FPV pilots to import, safely edit, and export Betaflight CLI configuration files — no installation required.

**Live tool:** https://fpvthings.github.io/Betaflight-Config-Editor/

---

## What This Tool Does

Betaflight stores its configuration as a set of CLI commands. When you export a config using `diff all` in the CLI tab, you get a plain text file full of `set parameter = value` lines. These files are powerful but dense — hundreds of parameters with no explanation of what's safe to change, what's hardware-specific, and what will break your build if copied blindly.

This tool turns that text file into a structured, tabbed form — the same layout you're used to from Betaflight Configurator — so you can review and edit settings confidently, then download a clean `.txt` ready to paste back into the CLI.

It's designed for pilots who are comfortable in Betaflight Configurator but haven't spent much time in the CLI. It's also useful for experienced pilots who want a faster way to adapt a community config to their own build.

---

## Who It's For

- You've found a community config for a quad similar to yours and want to adapt it
- You want to tweak PIDs, rates, or filtering without hunting through hundreds of raw CLI lines
- You're new to CLI editing and want guardrails before pasting anything into your flight controller
- You want to transfer your switch assignments (modes) or rates to a fresh config

---

## Important: What You Must Still Do Yourself

This tool will not — and cannot — make your config safe to flash without your attention. Before applying any exported config to your quad, you are responsible for the following:

### Hardware-Specific Values — Never Copy Between Builds

Some parameters are calibrated to a specific physical flight controller and are meaningless (or dangerous) when copied to a different board. This tool flags them as read-only and preserves them from your own imported config. **They are not editable for a reason.**

| Parameter | Why It Must Not Be Copied |
|---|---|
| `acc_calibration` | IMU calibration unique to each physical board — always re-run after flashing |
| `vbat_scale` | Voltage sensor calibration — verify with a multimeter on your specific unit |
| `ibata_scale` | Current sensor calibration — calibrate against a known current draw |
| `align_board_*` / `gyro_1_align_*` | How the FC is physically oriented in the frame — differs per build |
| `motor_output_reordering` | Matches motor wiring on the specific build — verify your own |
| `resource MOTOR` | Pin assignments for a specific AIO board revision — confirm for your board |

### After Every Flash

1. **Re-run Accelerometer Calibration** — go to Setup tab in Betaflight Configurator and calibrate
2. **Verify motor order and spin direction** — props off, use the Motors tab
3. **Confirm props-off arming test** — verify modes and arming work as expected before props go on
4. **Check voltage reading** — confirm the battery voltage shown in Configurator matches a multimeter reading

---

## How to Use

### Step 1 — Get a config to import

You need a Betaflight `diff all` export as a `.txt` file. This can be:

- A community config from [FPVTHINGS/Betaflight-Configs](https://github.com/FPVTHINGS/Betaflight-Configs) or any other shared source
- Your own backup — export from Betaflight Configurator → CLI tab → type `diff all` → **Save to File**
- Raw CLI text pasted directly from anywhere

### Step 2 — Import it

Open the tool at https://fpvthings.github.io/Betaflight-Config-Editor/ and either:
- Click **Upload .txt file** and select your file, or
- Paste the raw CLI text into the paste field

Then click **Load Config**. The tool will detect your Betaflight version, craft name, and how many PID/rate profiles are present.

### Step 3 — Edit what you need

Navigate the tabs — the layout mirrors Betaflight Configurator:

| Tab | What You Can Edit |
|---|---|
| **Configuration** | Craft name, motor protocol, idle value, motor poles, throttle limits, failsafe, blackbox |
| **Power & Battery** | Cell voltage thresholds, battery capacity, sag compensation |
| **PID Tuning** | P/I/D/F per axis, D-Min/D-Max, I-term settings, feedforward, simplified tuning |
| **Filtering** | Gyro and D-term filters, dynamic notch, RPM filter weights |
| **Receiver** | Stick deadband, ELRS model ID and packet rate |
| **Video Transmitter** | VTX band, channel, power level, video system |
| **Modes** | Paste your own `mode_range` switch assignments |
| **Adjustments** | Paste your own `adjrange` lines |

**If a field shows "Not present in imported config"** — that parameter wasn't in the file you loaded. It will not be written to the export either. This is expected for parameters that match Betaflight defaults.

**Parameters shown in grey with a lock icon** are hardware-specific. They display the value from your imported file for reference but cannot be edited here.

### Step 4 — Export

Set your filename and click **Download .txt**. The exported file:
- Preserves your original header comments verbatim (build notes, warnings, hardware lists)
- Contains all the parameters from your import, updated with your changes
- Ends with `save` — ready to paste directly into Betaflight Configurator's CLI tab

### Step 5 — Apply to your flight controller

1. Open Betaflight Configurator and connect your FC
2. Go to the **CLI** tab
3. Open your exported `.txt` file in any text editor, select all, copy
4. Paste into the CLI input field and press Enter
5. The config applies automatically and saves

---

## Tips for CLI Beginners

**The CLI is not as scary as it looks.** A `diff all` export is just a list of settings. Each line sets one value. If something looks wrong you can always `defaults` to reset and start over.

**`diff all` vs `dump`** — Always use `diff all` for backups and sharing. `dump` exports every single parameter including defaults, making files huge and hard to read. `diff all` only includes values that differ from Betaflight defaults — much cleaner.

**Paste the whole file, not individual lines.** The config is designed to be pasted in one go. Profile headers (`profile 0`, `rateprofile 0`) must be present for the right values to land in the right place.

**The `save` at the end matters.** Without it, changes are applied in RAM but lost on reboot. This tool always includes `save` in the export.

**You can always re-export from your FC.** If you're unsure what's currently on your quad, type `diff all` in the CLI tab and save the output. That's your current state.

**Backup before you flash anything new.** Take a `diff all` export from your FC before applying any community config. Keep it somewhere safe. It's your undo button.

---

## What This Tool Does Not Edit

The following are intentionally excluded — they are either too hardware-specific to edit safely, or too complex to represent correctly in a form:

- All OSD element positions (preserved verbatim in the export)
- `vtxtable` entries (preserved verbatim — too many interdependencies)
- `resource` pin assignments (hardware-specific PCB layout)
- Gyro and board alignment (`align_board_*`, `gyro_1_sensor_align`)
- Motor output reordering (wiring-specific)
- Accelerometer calibration

---

## Compatibility

The parser accepts any valid Betaflight `diff all` export regardless of:
- Betaflight version (auto-detected from the file header)
- Whether the file has custom comment headers or none at all
- Number of PID profiles or rate profiles

Files from community repos, personal backups, or pasted directly from the CLI all work.

---

## Contributing / Feedback

Issues, suggestions, and pull requests welcome at:
https://github.com/FPVTHINGS/Betaflight-Config-Editor

Community configs that work well with this tool:
https://github.com/FPVTHINGS/Betaflight-Configs

---

*Fly responsibly. Always verify settings on your specific hardware before arming with props on.*
