---
title: "Omnisonde"
subtitle: "Technical Documentation"
author: [Omnisonde]
date: "2026-06-07 01:54 UTC"
subject: "Auto-generated project documentation"
lang: "en"
titlepage: true
titlepage-rule-height: 2
titlepage-rule-color: "C8A24E"
titlepage-logo: "omnisonde.png"
logo-width: 220pt
page-background: "page-bg.png"
toc: true
toc-own-page: true
toc-title: "Contents"
toc-depth: 3
colorlinks: true
header-includes:
  - "\\usepackage{longtable}"
  - "\\AtBeginEnvironment{longtable}{\\footnotesize}"
---

::: {.generated-note}
*This document is generated automatically from the Omnisonde codebase (commit `c594124`) on 2026-06-07 01:54 UTC. Do not edit it by hand — update the source and re-run `docs/generator/build_docs.py`.*
:::

# Introduction

Omnisonde is a local-first circuit-board probing workflow for hardware debugging, reverse engineering, and validation. Engineers upload PCB images, mark probe points, and run repeatable scan sessions that capture data from oscilloscopes, logic analyzers, power-supply automation, and other lab instruments at each point. Captures are tied to physical board locations, run through protocol analysis, and rolled up into shareable reports.

This document covers the user-facing workflow as well as the internal architecture, the plugin/hook/analysis extension points, the REST API, the configuration file, and the database schema. The reference sections are extracted directly from the codebase so they stay accurate as the project evolves.

## Getting Started

Omnisonde uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync                 # install dependencies
uv run python main.py   # start the dev server on 0.0.0.0:5000
```

Open `http://localhost:5000` in a browser, create or select a project, upload a board image, and start placing probe points.

# Installation & Setup

Omnisonde runs as a local Flask web application. It is designed to sit on a
bench machine that can reach your instruments (oscilloscope, power supply,
logic analyzer, and optionally a GRBL motion table).

## Requirements

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** for dependency management
- Instrument access as needed: a VISA backend for SCPI instruments
  (`pyvisa` + `pyvisa-py` are installed by default), `sigrok-cli` for
  sigrok-compatible logic analyzers, and a serial port for the XYZ table.

## Install

```bash
git clone <your-fork-or-clone-url> omnisonde
cd omnisonde
uv sync
```

Optional dependency groups:

```bash
uv sync --extra thermal   # OpenCV-based extras
uv sync --extra docs      # Playwright, for the documentation screenshot capture
```

## Run

```bash
uv run python main.py
```

The development server listens on `0.0.0.0:5000`. Open
`http://localhost:5000` in a browser.

![The empty state — upload or select a board image to begin.](../screenshots/01_empty_state.png)

No instruments are required to start the app or to place probe points;
instrument connections are only opened when a scan actually runs, so you can
lay out a board and plan a scan entirely offline.

\newpage

# Your First Scan

This walkthrough takes you from a blank project to captured, analyzed data.

## 1. Create a project and upload a board

A **project** groups related board images, scans, and configuration. Pick a
project in the header (or create one), then upload a PCB image with
**Upload**. Coordinates are stored as percentages of the image, so the same
probe points stay correct regardless of zoom or display resolution.

## 2. Place probe points

Click anywhere on the board to drop a probe point. Select a point to rename
it and assign a **signal name** (e.g. `UART_TX`, `3V3`, `CLK`) and an
optional group. The right sidebar lists every point and supports search and
filtering by name, signal, voltage range, protocol, or pass/fail status.

![Board view with probe points marked and the point list in the sidebar.](../screenshots/02_board_view.png)

Points are saved automatically. Use the scroll wheel to zoom, middle-click to
pan, and the minimap (bottom-right when zoomed) to navigate.

## 3. Configure and run a scan

Switch to **Scan** mode. Select one or more instrument plugins (oscilloscope,
logic analyzer, multimeter, …) and any lifecycle hooks, set the power-on
timeout, and press **Run Scan**.

![Scan mode: choose plugins and hooks, set the timeout, and run.](../screenshots/03_scan_mode.png)

Each point runs through the scan lifecycle: move (if a calibrated XYZ table
is configured) → prepare instruments → power on → capture → run hooks →
power off → save. A live status bar shows progress, and after each point you
can **Continue** or **Retry**. Check only the points you want if you don't
need a full sweep.

## 4. Analyze the results

Switch to **Analyze** mode to browse scan history. Press **Analyze** on a
scan to run protocol detection across its captures; detected protocols
(UART, eMMC, …) appear as badges with expandable parameters, and decoded
output is shown where available.

![Analyze mode: scan history with protocol-detection results.](../screenshots/04_analyze_mode.png)

From here you can also auto-label points from detections, evaluate against
pass/fail criteria, and set a scan as the **golden baseline** for anomaly
comparison.

\newpage

# Configuring Instruments

All instrument addresses and scan settings live in `config.json` and are
editable from the **Settings** panel — no manual file editing required. The
panel has a tab per instrument plus an auto-discovery helper that scans for
VISA resources on the host.

![Settings: tabbed instrument configuration with VISA auto-discovery.](../screenshots/07_settings.png)

## Scan settings

The `scan` section controls phase-level retry behavior:

- `retry_attempts` — how many times a failed phase (prepare/capture/save) is
  retried before the point is reported as failed.
- `retry_delay` — seconds to wait between retries. Connection errors trigger
  an automatic reconnect attempt.

## Instruments

Each instrument is configured under `instruments.<name>`:

- **power_supply** — VISA `resource_string`, `baud_rate`, `timeout`. The
  supply is powered on before capture and off afterward, around the
  configurable timeout.
- **oscilloscope** — `resource_string`, `waveform_channel`, and a `trigger`
  block (`channel`, `edge`, `threshold`, `coupling`). Per-point trigger
  overrides are supported and fall back to this global config.
- **xyz_table** — serial `port`, `baud_rate`, and Z heights (`travel_z`,
  `probe_z`) plus `feed_rate`. Motion only activates when a port is set *and*
  the image has calibration.
- **saleae** / **sigrok** — logic-analyzer capture settings (sample rate,
  duration, channels, triggers).
- **scpi_instrument** — a fully config-driven generic SCPI plugin: define
  `prepare_commands`, `capture_queries`, an optional `screenshot_command`,
  and a `waveform` block, with no code required.
- **multimeter** — a DMM `resource_string`, `timeout`, and the list of
  measurement `functions` to run per point.

The exact, always-current key list for every section appears in the
*Configuration Reference* later in this document, which is generated from the
live `config.json`.

## Connecting ad-hoc with the SCPI terminal

For one-off commands, the **SCPI Terminal** connects to any VISA resource and
lets you send writes and queries interactively — useful for confirming an
address or trigger setting before committing it to a scan.

\newpage

# Calibration & the XYZ Table

The XYZ-table integration is entirely optional. When a GRBL motion table is
configured *and* the current image has a calibration, Omnisonde
auto-positions the probe over each point during a scan.

## How calibration works

Calibration maps **image coordinates** (the percentage positions where you
placed probe points) to **physical coordinates** (millimetres on the table)
using an affine transform. Because the mapping is per-image, every board gets
its own calibration.

## 3-point calibration

1. Connect to the table (Settings → XYZ Table, or the calibration overlay's
   jog controls).
2. Jog the probe to a known feature on the board and record it as
   calibration point 1; repeat for points 2 and 3. Three non-collinear
   points fully determine the affine transform.
3. Once all three are recorded, scans for that image will move the probe to
   each point automatically, lowering to `probe_z` to probe and raising to
   `travel_z` to move.

## Region calibration

For larger boards you can define rectangular **regions** and calibrate each
independently. After adding anchor points to a region, fit its transform; the
app reports the RMS and maximum fit error so you can judge accuracy, and you
can verify the fit by moving to a known point and recording the position
error in millimetres.

If no table is configured, none of this is required — scans simply skip the
move/retract phases and you probe by hand.

\newpage

# Schematic Cross-Reference

Omnisonde can tie each probe point to a **net name** from your schematic, so a
capture reads as "TP14 = `SDRAM_CLK` (U1.5, U3.12)" instead of an anonymous dot
on a photo. This is the bridge between physical probing and design intent — and
it flows straight into reports.

## Importing a netlist

In **Project** mode, click **Import Netlist** and choose either:

- a **KiCad** netlist exported from eeschema (`.net`, the S-expression
  format), or
- a **CSV pin map** with a header naming a net/signal column (and optional
  `ref`, `pin`, `function` columns), e.g.:

  ```csv
  net,ref,pin,function
  SDRAM_CLK,U1,5,CLK
  SDRAM_CLK,U3,12,
  GND,U1,1,
  ```

The status line shows how many nets and pins were imported. Re-importing
replaces the previous netlist for that image; **Clear Netlist** removes it
(point assignments are kept).

## Assigning nets to points

Expand a probe point and use the **Net** field — it auto-completes from the
imported net names. Once assigned, the point row shows a `⌁ net` tag and the
detail panel lists the connected component pins.

### Auto-map

**Auto-map Nets** assigns nets automatically by matching each point's signal
name (then its point name) to a net, ignoring case and `/ - . space`
differences (so `uart-tx` matches `/UART_TX`). It only fills in points that
don't already have a net, so manual assignments are never overwritten.

## In reports

Assigned nets appear in each point's section of the generated report (**Net:
…**), giving the reader a design-level reference alongside the capture and
measurements.

\newpage

# Reports & Analysis

Omnisonde turns captured scans into shareable, validation-grade reports.

## Protocol detection

Analysis runs on captured files at rest (not during capture, to avoid stale
data). The bundled analyzers detect UART and eMMC bus activity from raw
oscilloscope binaries and sigrok CSVs, characterize signals
(clock/data/power/PWM/…), and cluster probe-point voltages into standard
rails. Re-analyzing a scan clears prior detections first, so results never
accumulate stale entries.

## Generating reports

From **Reports** mode (or the **Reports** action on a scan), Omnisonde
generates a report set from a single Markdown source:

- **Markdown** — the source document.
- **HTML** — a styled, self-contained page.
- **PDF** — via pandoc + the eisvogel template.

### Interactive datasheet

The **Datasheet** action on a scan opens an *interactive* board datasheet — a
single self-contained HTML file you can hand to a colleague or client. The
board photo carries clickable probe-point markers (colored by pass/fail);
clicking a marker jumps to that point's card. A search box filters points by
name, signal, net, or protocol, and each card shows the schematic net and
connected pins, voltage, decoded protocols, and the capture screenshot
(click to zoom). Images are embedded, so it works fully offline. Unlike the
Markdown/PDF reports (static documents), this is the interactive deliverable.

![Reports mode: generated Markdown / HTML / PDF report sets.](../screenshots/05_reports_mode.png)

A report includes an executive summary, scan and instrumentation details,
validation configuration and results, per-point captures with zoomed crops,
an anomaly summary, and a conclusion. If a scan has no cached detections when
a report is requested, analysis runs automatically first.

## Baselines and comparison

Mark a trusted scan as the **golden baseline** for an image, then compare
later scans against it to surface anomalies, or diff any two scans directly.
The **timeline** view tracks per-point voltage and detection trends across a
board's scan history.

> **Note** — this per-scan report pipeline (`analysis/report_generator.py`)
> is distinct from the project documentation you are reading, which is
> produced by `docs/generator/`.

\newpage

# Protocol Decoding

Omnisonde decodes bus traffic two ways: built-in heuristics, and sigrok's full
decoder library.

## Built-in detection

The bundled `protocol_detection` analyzer identifies **UART** (with baud rate
and a decoded-text preview) and **eMMC** bus activity directly from raw
oscilloscope binaries and sigrok CSVs — no configuration required. It's ideal
for a single-probe scope capture where you don't yet know what a signal is.

## Full decoding via sigrok (`sigrok_decode`)

For real transaction decoding across many buses — **I2C, SPI, CAN, UART,
1-Wire, USB, and 50+ others** — Omnisonde runs sigrok's protocol decoders
(libsigrokdecode) through `sigrok-cli`. This needs two things:

1. **A sigrok session capture.** Protocol decoders need multiple named channels
   (e.g. I2C's `scl` + `sda`), so capture with the sigrok logic-analyzer plugin
   and set its `output_format` to `sr`.
2. **`sigrok-cli` installed** on the host.

Then add decoders in **Settings → Sigrok → Protocol Decoders**: tick *Decode
captured sessions…*, click **+ Add decoder**, and for each row enter the
decoder name (the field auto-completes from your installed decoders), its
channel map (`scl=D0, sda=D1`), and any options (`baudrate=115200`). These are
stored under `analysis.sigrok_decode` in the config, which you can also edit
directly:

```json
"analysis": {
  "sigrok_decode": {
    "enabled": true,
    "max_preview_rows": 40,
    "decoders": [
      { "decoder": "uart", "channels": { "rx": "D0" }, "options": { "baudrate": 115200 } },
      { "decoder": "i2c",  "channels": { "scl": "D0", "sda": "D1" } },
      { "decoder": "spi",  "channels": { "clk": "D0", "mosi": "D1", "miso": "D2", "cs": "D3" } }
    ]
  }
}
```

Each entry's `channels` map a decoder's inputs to your capture's channel names,
and `options` pass decoder parameters (UART needs `baudrate`; many others work
with defaults). When a scan is analyzed, every configured decoder runs over each
sigrok capture and decoded transactions appear as protocol badges with a
decoded-output preview — the same place built-in detections show up.

The plugin is a no-op unless decoders are configured, so it's safe to leave
enabled. The decoder-name field in Settings lists what your `sigrok-cli`
supports; for the full option reference of a decoder, run
`sigrok-cli --show --protocol-decoder <id>`.

\newpage

# Interface & Shortcuts

## Navigation modes

The left sidebar switches between modes: **View** (browse and place points),
**Scan** (configure and run), **Analyze** (scan history and detections),
**Reports** (saved report sets), **Project** (rename/delete images, export
and import projects), and **Settings** (instrument configuration).

![Project mode: rename or delete images and export/import projects.](../screenshots/06_project_mode.png)

Projects export and import as ZIP archives with full scan data and
detections, so a board investigation can be handed off or archived intact.

## Keyboard shortcuts

Press **?** anywhere to open the shortcut reference.

![The keyboard-shortcut overlay.](../screenshots/08_keyboard_help.png)

| Key | Action |
|---|---|
| `?` | Show / hide the shortcut help |
| `/` | Focus the point search box |
| `v` | Toggle the voltage overlay |
| `t` | Toggle light / dark theme |
| `+` / `-` / `0` | Zoom in / out / reset |
| `Del` | Delete the selected point |
| `Esc` | Close dialogs and overlays |

## Feedback conventions

Status messages appear as non-blocking **toasts** (success, warning, error,
info) that auto-dismiss and never interrupt your work.

![Toast notifications.](../screenshots/09_toasts.png)

Long-running actions and list loads show a spinner so the UI never appears
frozen, and a guard warns before you navigate away while a scan is running.

![Loading feedback while data is in flight.](../screenshots/10_loading_state.png)

The interface uses a light/dark theme (toggle with `t`, persisted across
sessions), landmark roles and labels for assistive technology, and focus
trapping in dialogs.

\newpage

# Extending: Writing an Instrument Plugin

Instrument **plugins** control live instruments during a scan and produce
captures (screenshots, waveforms, measurements). They live in `plugins/` and
are auto-discovered at runtime — no manual registration.

## Anatomy

Subclass `ScanPlugin` from `plugins.base`, set the class attributes, and
implement the lifecycle methods:

```python
from plugins.base import ScanPlugin, PluginResult


class MyInstrumentPlugin(ScanPlugin):
    name = "my_instrument"            # registry key (matches config section)
    display_name = "My Instrument"    # label shown in the UI
    requires_power_supply = True      # whether the scan powers the DUT

    def __init__(self, config: dict) -> None:
        # config is instruments.my_instrument from config.json
        self.resource = config.get("resource_string", "")
        # open your connection here

    def prepare(self, point: dict, output_dir: str) -> None:
        # before power-on: arm trigger, configure capture
        ...

    def capture(self, point: dict, output_dir: str) -> None:
        # after power-on + timeout: stop acquisition / wait for data
        ...

    def save(self, point: dict, output_dir: str) -> PluginResult:
        # write files into output_dir and return their paths
        return PluginResult(
            plugin_name=self.name,
            screenshot_path="...",          # optional
            waveform_path="...",            # optional
            measurements={"voltage": 3.3},  # optional scalars
        )

    def close(self) -> None:
        # release instrument resources at session end
        ...
```

## Lifecycle

The runtime calls, per probe point and in order:
`prepare` → (power on) → `capture` → `save`, then `close` once at session end.
Optionally override `reconnect()` so the runtime can recover from connection
errors during its per-phase retry.

## Results and the voltage overlay

`PluginResult.measurements` carries scalar values alongside file artifacts.
Storing a `voltage` key feeds the board's voltage overlay and report metrics.
Only populate measurements when the instrument actually produced data (e.g.
the scope genuinely triggered), so stale values never leak into reports.

## Configuration

Add an `instruments.my_instrument` section to `config.json`; its contents are
handed to your `__init__` as `config`. For many SCPI instruments you may not
need code at all — the generic `scpi_instrument` plugin is fully
config-driven.

\newpage

# Extending: Writing a Scan Hook

**Hooks** run your own Python at specific points in the scan lifecycle —
toggling a GPIO, sending a fixture command, logging an event — *without*
producing captures. They live in `hooks/` and are auto-discovered, the same
way plugins are.

## Anatomy

Subclass `ScanHook` from `hooks.base`. Only `__init__` is required; the two
hook points default to no-ops, so override just the ones you need:

```python
from hooks.base import ScanHook, HookResult


class MyHook(ScanHook):
    name = "my_hook"
    display_name = "My Hook"

    def __init__(self, config: dict) -> None:
        # config is hooks.my_hook from config.json (or {} if unconfigured)
        ...

    def before_power_on(self, point: dict, output_dir: str) -> HookResult | None:
        # after instruments are armed, before the PSU turns on
        return HookResult(hook_name=self.name, message="armed fixture")

    def after_capture(self, point: dict, output_dir: str) -> HookResult | None:
        # after all plugins have captured, before the PSU turns off
        return None

    def close(self) -> None:
        # release resources at session end (default no-op)
        ...
```

## Lifecycle

Per probe point: `before_power_on` runs after instruments are prepared but
before power is applied; `after_capture` runs once all plugins have captured
but before power is removed. `__init__` and `close` bookend the session.

Selected hooks appear as checkboxes in **Scan** mode (with an orange accent
to distinguish them from capture plugins). See `hooks/example_log.py` for a
minimal working example that writes a timestamped log entry at each hook
point.

\newpage

# Extending: Writing an Analysis Plugin

**Analysis plugins** run *after* a scan, operating on captured files at rest
rather than live instruments. They are stateless and auto-discovered from the
`analysis/` directory.

## Anatomy

Subclass `AnalysisPlugin` from `analysis.base` and implement a single method:

```python
from analysis.base import AnalysisPlugin, AnalysisResult


class MyAnalyzer(AnalysisPlugin):
    name = "my_analyzer"
    display_name = "My Analyzer"

    def analyze(self, scan_result: dict, output_dir: str) -> AnalysisResult:
        # scan_result: id, scan_id, point_id, point_name,
        #   screenshot_path, waveform_path, plugin_name, timestamp
        # output_dir: where the scan's files live
        return AnalysisResult(
            plugin_name=self.name,
            detections=[...],   # protocol findings
            metrics={...},      # numeric stats
            files={...},        # any generated output paths
        )
```

## What to return

`AnalysisResult` carries three payloads:

- `detections` — protocol findings (surface as badges and in reports).
- `metrics` — numeric statistics (min/max/mean, duty cycle, etc.).
- `files` — paths to any artifacts your analyzer generates.

The plugin is invoked once per scan result. Because analyzers are stateless
and instantiated without arguments, they can run on exported scan ZIPs or raw
scan directories offline as well as in-app. The bundled analyzers
(`protocol_detection`, `waveform_stats`, `sigrok_export`) are good references.

\newpage

# Troubleshooting

## The app starts but a scan fails immediately

Instrument connections open only when a scan runs. A failure at the
`preparing` phase usually means an address or connection problem:

- Confirm the `resource_string` for each selected instrument in **Settings**.
- Use **Discover Instruments** (Settings) or the **SCPI Terminal** to verify
  the instrument responds to `*IDN?`.
- Errors are classified (timeout / connection / instrument / unknown) and the
  runtime retries each phase `scan.retry_attempts` times with
  `scan.retry_delay` between attempts, reconnecting on connection errors.

## The oscilloscope captures look empty or stale

The oscilloscope plugin arms a single trigger and polls for the trigger
state before capturing, and only records voltage/frequency measurements when
the scope actually triggered. If captures are empty, check the trigger
configuration (channel, edge, threshold, coupling) globally or per point.

## The XYZ table doesn't move during a scan

Motion activates only when a `port` is configured **and** the current image
has a calibration. Verify both, and that homing/unlock succeeded if the
controller is in an alarm state.

## Protocol detection finds nothing

Detection runs on captured files after the scan. Make sure the scan actually
produced waveform/CSV files, then press **Analyze** on the scan. UART
detection runs first and eMMC is skipped when UART is found, to avoid false
positives on idle-high lines.

## PDF reports aren't generated

PDF export needs either a running Docker daemon (the `pandoc/extra` image) or
a local `pandoc` plus a XeLaTeX engine. Markdown and HTML reports do not
require LaTeX. The same applies to building this documentation.

## Resetting local state

The SQLite database (`probe_points.db`), uploaded images (`uploads/`), and
scan output directories are local and gitignored. Removing them resets the
app to a clean state without affecting the code.

\newpage

# Architecture

Omnisonde is a Flask application backed by SQLite, with a single-page HTML/JS frontend. Instrument integration, scan-lifecycle hooks, and post-scan analysis are all pluggable and auto-discovered at runtime.

## Module Map

| Module | Responsibility |
|---|---|
| `app.main` | Omnisonde - Circuit board probe point manager with multi-instrument integration. |
| `app.persistence.probe_manager` | ProbeManager - Handles probe point management and future SCPI integration. |
| `app.runtime.probe_scan` | Scan session orchestration. |
| `app.runtime.scopectl` | Oscilloscope control over VISA/SCPI (Rigol). |
| `app.runtime.powerctl` | Power-supply control over VISA/SCPI. |
| `app.runtime.motionctl` | GRBL XYZ-table control over serial. |
| `app.runtime.calibration` | Affine transform calibration for mapping image coordinates (%) to physical coordinates (mm). |
| `app.runtime.sigrok_utils` | Sigrok session file (.sr) utilities. |
| `protocol_detect` | Protocol detection and waveform-analysis helpers. |
| `plugins.base` | Scan plugin contract. |
| `hooks.base` | Scan hook contract. |
| `analysis.base` | Analysis plugin contract. |
| `analysis.report_generator` | Unified report generator — single Markdown source for both HTML and PDF. |

## Extension Points

- **Plugins** (`plugins/`) control live instruments during a scan and produce captures (screenshots, waveforms, measurements).
- **Hooks** (`hooks/`) run user code at scan-lifecycle points (before power-on, after capture) without producing captures.
- **Analysis plugins** (`analysis/`) operate on captured files at rest to produce protocol detections, metrics, and derived artifacts.

All three are discovered automatically: drop a subclass into the relevant directory and it is registered with no manual wiring.

# Instrument Plugins

Plugins control live instruments during a scan. Each is selectable in Scan mode and configured under its `instruments.<name>` config section.

| Name | Display Name | Description |
|---|---|---|
| `multimeter` | Multimeter | — |
| `oscilloscope` | Oscilloscope | — |
| `saleae` | Saleae | — |
| `scpi_instrument` | SCPI Instrument | — |
| `sigrok` | Sigrok | Capture logic analyzer data using sigrok-cli (sigrok command-line interface). |

Notable attributes:

- **multimeter** — `requires_power_supply=True`
- **oscilloscope** — `requires_power_supply=True`
- **saleae** — `requires_power_supply=True`
- **scpi_instrument** — `requires_power_supply=True`
- **sigrok** — `requires_power_supply=True`

# Scan Hooks

Hooks run custom Python at scan-lifecycle points without producing captures.

| Name | Display Name | Description |
|---|---|---|
| `log` | Log to File | Writes a log entry for each probed point. |

# Analysis Plugins

Analysis plugins run on captured files after a scan to produce protocol detections, metrics, and derived artifacts.

| Name | Display Name | Description |
|---|---|---|
| `protocol_detection` | Protocol Detection | — |
| `sigrok_decode` | Sigrok Protocol Decode | — |
| `sigrok_export` | Sigrok Export (.sr) | — |
| `waveform_stats` | Waveform Statistics | — |

# Configuration Reference

All instrument addresses and scan settings live in `config.json`, editable from the Settings panel. The current structure is:

```json
{
  "scan": {
    "retry_attempts": 2,
    "retry_delay": 1.0
  },
  "instruments": {
    "power_supply": {
      "resource_string": "ASRL/dev/ttyUSB0::INSTR",
      "baud_rate": 115200,
      "timeout": 50000
    },
    "oscilloscope": {
      "resource_string": "TCPIP::192.168.0.103::INSTR",
      "waveform_channel": "1",
      "trigger": {
        "channel": "1",
        "edge": "rising",
        "threshold": 1,
        "coupling": "dc"
      }
    },
    "xyz_table": {
      "port": "",
      "baud_rate": 115200,
      "travel_z": 10,
      "probe_z": 0,
      "feed_rate": 500
    },
    "saleae": {
      "host": "localhost",
      "device_id": "",
      "port": 10430,
      "sample_rate": 25000000,
      "capture_duration": 5,
      "digital_channels": [
        0,
        1,
        2,
        3
      ],
      "analog_channels": [],
      "digital_threshold_volts": null,
      "analog_downsample_ratio": 1
    },
    "sigrok": {
      "driver": "fx2lafw",
      "serial": "",
      "sample_rate": 24000000,
      "capture_duration": 5,
      "channels": "D0,D1,D2,D3",
      "triggers": "",
      "output_format": "csv"
    },
    "scpi_instrument": {
      "resource_string": "",
      "timeout": 10000,
      "requires_power_supply": true,
      "prepare_commands": [],
      "capture_queries": [],
      "screenshot_command": "",
      "waveform": {
        "setup_commands": [],
        "data_query": ""
      }
    },
    "multimeter": {
      "resource_string": "",
      "timeout": 10000,
      "functions": [
        "dc_voltage"
      ]
    }
  },
  "analysis": {
    "sigrok_decode": {
      "enabled": false,
      "max_preview_rows": 40,
      "decoders": []
    }
  }
}
```

## Instrument Sections

| Section | Keys |
|---|---|
| `power_supply` | `resource_string`, `baud_rate`, `timeout` |
| `oscilloscope` | `resource_string`, `waveform_channel`, `trigger` |
| `xyz_table` | `port`, `baud_rate`, `travel_z`, `probe_z`, `feed_rate` |
| `saleae` | `host`, `device_id`, `port`, `sample_rate`, `capture_duration`, `digital_channels`, `analog_channels`, `digital_threshold_volts`, `analog_downsample_ratio` |
| `sigrok` | `driver`, `serial`, `sample_rate`, `capture_duration`, `channels`, `triggers`, `output_format` |
| `scpi_instrument` | `resource_string`, `timeout`, `requires_power_supply`, `prepare_commands`, `capture_queries`, `screenshot_command`, `waveform` |
| `multimeter` | `resource_string`, `timeout`, `functions` |

# REST API Reference

The application exposes 102 routes. Methods, paths, and summaries are extracted from the live Flask URL map.

| Method | Path | Description |
|:------------|:----------------------------------|:--------------------------|
| GET | `/` | Main page with image upload and point selection UI. |
| GET | `/api/analysis-plugins` | List the available post-scan analysis plugins. |
| GET | `/api/calibration/<image_path>` | Return the 3-point affine calibration for an image, if any. |
| DELETE | `/api/calibration/<image_path>` | Delete an image's calibration. |
| POST | `/api/calibration/<image_path>/point` | Record one of the three calibration points for an image. |
| GET | `/api/config` | Return current instrument configuration. |
| PUT | `/api/config` | Update instrument configuration. |
| GET | `/api/criteria/<image_path>` | Get pass/fail criteria for an image. |
| POST | `/api/criteria/<image_path>` | Set pass/fail criteria for a probe point. |
| DELETE | `/api/criteria/<int:criteria_id>` | Delete a pass/fail criteria entry. |
| GET | `/api/detections/<image_path>/by-point` | Return protocol detections for an image grouped by probe point. |
| GET | `/api/environment-check` | Return environment checks for the recommended release-1 support scope. |
| GET | `/api/hooks` | Return available scan hooks. |
| GET | `/api/images` | List images, optionally filtered by project. |
| DELETE | `/api/images/<image_path>` | Delete an image and all associated data. |
| PUT | `/api/images/<image_path>/rename` | Rename an image's display name. |
| POST | `/api/motion/connect` | Connect to the configured XYZ table over serial. |
| POST | `/api/motion/disconnect` | Disconnect from the XYZ table. |
| POST | `/api/motion/home` | Run the GRBL homing cycle. |
| POST | `/api/motion/jog` | Jog the table by a relative offset (axis/distance in the request body). |
| POST | `/api/motion/move` | Move the table to an absolute position from the request body. |
| GET | `/api/motion/position` | Return the table's current machine position. |
| POST | `/api/motion/unlock` | Clear a GRBL alarm/lock state. |
| POST | `/api/motion/zero` | Zero the work coordinate system at the current position. |
| GET | `/api/netlist/<image_path>` | Return the imported netlist for an image (summary + nets), or empty. |
| POST | `/api/netlist/<image_path>` | Parse and store an uploaded KiCad ``.net`` or CSV netlist for an image. |
| DELETE | `/api/netlist/<image_path>` | Delete the imported netlist for an image. |
| POST | `/api/netlist/<image_path>/automap` | Assign net names to points by matching point signal/name to net names. |
| GET | `/api/plugins` | Return available scan plugins. |
| POST | `/api/points` | Add a new probe point. |
| GET | `/api/points/<image_path>` | Get all points for an image. |
| GET | `/api/points/<image_path>/export` | Export points as JSON. |
| GET | `/api/points/<image_path>/export-svg` | Export probe points as an SVG overlay with labels. |
| GET | `/api/points/<image_path>/next-name` | Get suggested name for next point. |
| PUT | `/api/points/<int:point_id>` | Update a probe point. |
| DELETE | `/api/points/<int:point_id>` | Delete a probe point. |
| GET | `/api/points/<int:point_id>/evidence` | Return the captured evidence (results/detections) for a probe point. |
| POST | `/api/project/export` | Export a project (by image_path) as a downloadable ZIP archive. |
| POST | `/api/project/import` | Import an uploaded project ZIP into a new project. |
| GET | `/api/projects` | List all projects. |
| POST | `/api/projects` | Create a new project. |
| GET | `/api/projects/<int:project_id>` | Get a single project. |
| PUT | `/api/projects/<int:project_id>` | Update a project's name, description, or config. |
| DELETE | `/api/projects/<int:project_id>` | Delete a project and all its data. |
| GET | `/api/projects/<int:project_id>/config` | Get instrument config for a project. |
| PUT | `/api/projects/<int:project_id>/config` | Update instrument config for a project. |
| GET | `/api/query/scan-points` | Search probe points across scans by name, signal, voltage, or protocol. |
| GET | `/api/region-calibration/<image_path>` | List the rectangular region calibrations defined for an image. |
| POST | `/api/region-calibration/<image_path>` | Create a rectangular region calibration for an image. |
| DELETE | `/api/region-calibration/<int:region_id>` | Delete a region calibration and its anchors. |
| POST | `/api/region-calibration/<int:region_id>/anchor` | Record an image-to-physical anchor point for a region calibration. |
| POST | `/api/region-calibration/<int:region_id>/fit` | Fit the region's affine transform from its anchors and report fit error. |
| POST | `/api/region-calibration/<int:region_id>/move-point` | Move the table to a probe point's predicted physical position. |
| GET | `/api/region-calibration/<int:region_id>/predictions` | Return predicted physical positions for the region's probe points. |
| POST | `/api/region-calibration/<int:region_id>/verify-point` | Record a verification measurement for a region calibration. |
| GET | `/api/report/<int:report_id>` | Serve a saved report file (HTML/PDF/Markdown) by id. |
| DELETE | `/api/report/<int:report_id>` | Delete a saved report (DB row and file on disk). |
| GET | `/api/reports/<image_path>` | List saved report sets for an image. |
| GET | `/api/scan-templates` | List all saved scan templates. |
| POST | `/api/scan-templates` | Save a scan template. |
| DELETE | `/api/scan-templates/<int:template_id>` | Delete a scan template. |
| DELETE | `/api/scan/<int:scan_id>` | Delete a scan and optionally its files. |
| POST | `/api/scan/<int:scan_id>/analyze` | Run protocol detection across all results of a scan. |
| POST | `/api/scan/<int:scan_id>/auto-label` | Label probe points from a scan's protocol detections. |
| POST | `/api/scan/<int:scan_id>/baseline` | Mark a scan as the golden baseline for its image. |
| DELETE | `/api/scan/<int:scan_id>/baseline` | Clear a scan's golden-baseline flag. |
| GET | `/api/scan/<int:scan_id>/baseline-diff` | Compare a scan against its image's golden baseline. |
| GET | `/api/scan/<int:scan_id>/datasheet` | Generate and return the interactive HTML datasheet for a scan inline. |
| GET | `/api/scan/<int:scan_id>/detections` | Return cached protocol detections for a scan. |
| DELETE | `/api/scan/<int:scan_id>/detections` | Clear cached protocol detections for a scan. |
| GET | `/api/scan/<int:scan_id>/evaluate` | Evaluate a scan against pass/fail criteria. |
| GET | `/api/scan/<int:scan_id>/export` | Export a scan's output directory as a ZIP bundle. |
| GET | `/api/scan/<int:scan_id>/report` | Generate and return an HTML report for a scan inline. |
| GET | `/api/scan/<int:scan_id>/report/pdf` | Generate and download a standalone PDF report for a scan. |
| POST | `/api/scan/<int:scan_id>/reports` | Generate the full report bundle (Markdown + HTML + PDF) for a scan. |
| DELETE | `/api/scan/<int:scan_id>/reports` | Delete all saved reports for a scan; return how many files were removed. |
| GET | `/api/scan/<int:scan_id>/results` | Get results for a specific scan. |
| POST | `/api/scan/probe-point` | Run the full capture lifecycle for one probe point. |
| POST | `/api/scan/rescan-point` | Re-probe a single point (the frontend's Retry action). |
| POST | `/api/scan/result/<int:result_id>/analyze` | Run protocol detection on a single scan result. |
| POST | `/api/scan/session/cancel` | Request cancellation of the active scan session. |
| POST | `/api/scan/session/end` | End the scan session and release instruments. |
| POST | `/api/scan/session/start` | Start a scan session (selected plugins, hooks, and points). |
| GET | `/api/scan/session/status` | Return the current scan session's status. |
| GET | `/api/scans/<image_path>` | Get all scans for an image. |
| GET | `/api/scans/<image_path>/timeline` | Return a per-point voltage/detection timeline across an image's scans. |
| POST | `/api/scans/compare` | Compare two scans (scan_a vs scan_b) point by point. |
| GET | `/api/sigrok/decoders` | List the protocol decoders sigrok-cli supports (for the decoder editor). |
| GET | `/api/validation-status/<image_path>` | Return per-point pass/fail validation status for an image. |
| POST | `/api/visa/command` | Send a SCPI write/query and return the response. |
| POST | `/api/visa/connect` | Open a VISA session to the resource in the request body. |
| POST | `/api/visa/disconnect` | Close the active VISA session. |
| GET | `/api/visa/resources` | List VISA resource strings discovered on the host. |
| GET | `/api/visa/status` | Return whether a VISA session is open and to which resource. |
| GET | `/api/voltage-scan/<image_path>` | Return saved voltage readings for an image (drives the voltage overlay). |
| GET | `/help/sigrok` | Serve the Sigrok help page. |
| GET, POST | `/login` | Shared-token sign-in page (only meaningful when auth is enabled). |
| GET | `/logout` | Clear the authenticated session. |
| GET | `/scans/<path:filepath>` | Serve scan result files (screenshots, waveforms). |
| POST | `/upload` | Handle image upload. |
| GET | `/uploads/<filename>` | Serve uploaded images. |

# Database Schema

Omnisonde stores state in SQLite (16 tables). The schema below is read from a freshly initialized database.

## `calibrations`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `image_path` | TEXT |
| `point_index` | INTEGER |
| `img_x` | REAL |
| `img_y` | REAL |
| `phys_x` | REAL |
| `phys_y` | REAL |

## `images`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `path` | TEXT |
| `original_name` | TEXT |
| `project_id` | INTEGER |

## `net_nodes`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `net_id` | INTEGER |
| `ref` | TEXT |
| `pin` | TEXT |
| `pinfunction` | TEXT |

## `netlists`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `image_path` | TEXT |
| `original_name` | TEXT |
| `created_at` | TEXT |

## `nets`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `netlist_id` | INTEGER |
| `name` | TEXT |
| `code` | TEXT |

## `pass_fail_criteria`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `image_path` | TEXT |
| `point_id` | INTEGER |
| `voltage_min` | REAL |
| `voltage_max` | REAL |
| `expected_protocol` | TEXT |
| `expected_signal_type` | TEXT |
| `custom_label` | TEXT |

## `probe_points`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `name` | TEXT |
| `x` | REAL |
| `y` | REAL |
| `image_path` | TEXT |
| `signal_name` | TEXT |
| `notes` | TEXT |
| `group_name` | TEXT |
| `trigger_config` | TEXT |
| `net_name` | TEXT |

## `projects`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `name` | TEXT |
| `description` | TEXT |
| `config` | TEXT |
| `created_at` | TEXT |
| `updated_at` | TEXT |

## `protocol_detections`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `scan_result_id` | INTEGER |
| `protocol` | TEXT |
| `parameters` | TEXT |
| `confidence` | TEXT |
| `timestamp` | TEXT |

## `region_calibration_points`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `region_calibration_id` | INTEGER |
| `anchor_name` | TEXT |
| `img_x` | REAL |
| `img_y` | REAL |
| `phys_x` | REAL |
| `phys_y` | REAL |
| `created_at` | TEXT |

## `region_calibrations`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `image_path` | TEXT |
| `name` | TEXT |
| `x1` | REAL |
| `y1` | REAL |
| `x2` | REAL |
| `y2` | REAL |
| `transform_type` | TEXT |
| `transform_params` | TEXT |
| `fit_status` | TEXT |
| `rms_error` | REAL |
| `max_error` | REAL |
| `verified_point_id` | INTEGER |
| `verified_error_mm` | REAL |
| `verified_at` | TEXT |
| `created_at` | TEXT |
| `updated_at` | TEXT |

## `reports`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `scan_id` | INTEGER |
| `image_path` | TEXT |
| `format` | TEXT |
| `file_path` | TEXT |
| `timestamp` | TEXT |

## `scan_results`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `scan_id` | INTEGER |
| `point_id` | INTEGER |
| `point_name` | TEXT |
| `screenshot_path` | TEXT |
| `waveform_path` | TEXT |
| `timestamp` | TEXT |
| `plugin_name` | TEXT |
| `extra_files` | TEXT |

## `scan_templates`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `name` | TEXT |
| `plugins` | TEXT |
| `hooks` | TEXT |
| `power_timeout` | INTEGER |
| `trigger_config` | TEXT |
| `created_at` | TEXT |

## `scans`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `image_path` | TEXT |
| `scan_type` | TEXT |
| `output_dir` | TEXT |
| `timestamp` | TEXT |
| `is_baseline` | INTEGER |
| `project_id` | INTEGER |

## `voltage_readings`

| Column | Type |
|---|---|
| `id` | INTEGER |
| `image_path` | TEXT |
| `scan_id` | INTEGER |
| `point_id` | INTEGER |
| `voltage` | REAL |
| `timestamp` | TEXT |
| `voltage_min` | REAL |
| `voltage_max` | REAL |

# Python Module Reference

Public classes and functions for the core modules, extracted from source docstrings.

## `app.main`

`app/main.py`

Omnisonde - Circuit board probe point manager with multi-instrument integration.

- **`def login()`** — Shared-token sign-in page (only meaningful when auth is enabled).
- **`def logout()`** — Clear the authenticated session.
- **`def collect_environment_status()`** — Return environment checks for the recommended release-1 support scope.
- **`def index()`** — Main page with image upload and point selection UI.
- **`def sigrok_help()`** — Serve the Sigrok help page.
- **`def upload_image()`** — Handle image upload.
- **`def serve_upload(filename)`** — Serve uploaded images.
- **`def serve_scan_file(filepath)`** — Serve scan result files (screenshots, waveforms).
- **`def list_projects()`** — List all projects.
- **`def create_project()`** — Create a new project.
- **`def get_project(project_id)`** — Get a single project.
- **`def update_project(project_id)`** — Update a project's name, description, or config.
- **`def delete_project(project_id)`** — Delete a project and all its data.
- **`def get_project_config(project_id)`** — Get instrument config for a project.
- **`def update_project_config(project_id)`** — Update instrument config for a project.
- **`def list_images()`** — List images, optionally filtered by project.
- **`def get_points(image_path)`** — Get all points for an image.
- **`def add_point()`** — Add a new probe point.
- **`def update_point(point_id)`** — Update a probe point.
- **`def delete_point(point_id)`** — Delete a probe point.
- **`def get_next_name(image_path)`** — Get suggested name for next point.
- **`def export_points(image_path)`** — Export points as JSON.
- **`def get_netlist(image_path)`** — Return the imported netlist for an image (summary + nets), or empty.
- **`def upload_netlist(image_path)`** — Parse and store an uploaded KiCad ``.net`` or CSV netlist for an image.
- **`def delete_netlist(image_path)`** — Delete the imported netlist for an image.
- **`def automap_netlist(image_path)`** — Assign net names to points by matching point signal/name to net names.
- **`def rename_image(image_path)`** — Rename an image's display name.
- **`def delete_image(image_path)`** — Delete an image and all associated data.
- **`def list_plugins()`** — Return available scan plugins.
- **`def list_hooks()`** — Return available scan hooks.
- **`def get_scans(image_path)`** — Get all scans for an image.
- **`def get_scan_results(scan_id)`** — Get results for a specific scan.
- **`def export_scan(scan_id)`** — Export a scan's output directory as a ZIP bundle.
- **`def delete_scan(scan_id)`** — Delete a scan and optionally its files.
- **`def export_points_svg(image_path)`** — Export probe points as an SVG overlay with labels.
- **`def list_scan_templates()`** — List all saved scan templates.
- **`def save_scan_template()`** — Save a scan template.
- **`def delete_scan_template(template_id)`** — Delete a scan template.
- **`def get_criteria(image_path)`** — Get pass/fail criteria for an image.
- **`def set_criteria(image_path)`** — Set pass/fail criteria for a probe point.
- **`def delete_criteria(criteria_id)`** — Delete a pass/fail criteria entry.
- **`def evaluate_scan(scan_id)`** — Evaluate a scan against pass/fail criteria.
- **`def get_config()`** — Return current instrument configuration.
- **`def get_environment_check()`** — Return environment checks for the recommended release-1 support scope.
- **`def get_sigrok_decoders()`** — List the protocol decoders sigrok-cli supports (for the decoder editor).
- **`def update_config()`** — Update instrument configuration.
- **`def main()`** — Run the Flask development server.

## `app.persistence.probe_manager`

`app/persistence/probe_manager.py`

ProbeManager - Handles probe point management and future SCPI integration.

- **`class Project`** — Represents a project that groups related images, scans, and config.
    - `to_dict(self)` — Serialize to a plain dict for JSON API responses.
- **`class ProbePoint`** — Represents a single probe point on a circuit board image.
    - `to_dict(self)` — Serialize to a dict, parsing ``trigger_config`` JSON for API consumers.
- **`class ScanResult`** — Represents a scan result for a probe point.
    - `to_dict(self)` — Serialize to a plain dict for JSON API responses.
- **`class ProbeManager`** — Manages probe points for circuit board images.
    - `__init__(self, db_path)` — Open (and initialize, if needed) the SQLite database.
    - `create_project(self, name, description, config)` — Create a new project. If config is None, uses the global config.json.
    - `get_projects(self)` — Get all projects.
    - `get_project(self, project_id)` — Get a single project by ID.
    - `update_project(self, project_id, name, description, config)` — Update a project's name, description, and/or config.
    - `delete_project(self, project_id)` — Delete a project and all its images/scans. Refuses if it's the last project.
    - `get_project_config(self, project_id)` — Get parsed config dict for a project.
    - `add_point(self, name, x, y, image_path, signal_name)` — Add a new probe point.
    - `get_points(self, image_path)` — Get all probe points for a specific image.
    - `get_all_points(self)` — Get all probe points across all images.
    - `get_point(self, point_id)` — Get a specific probe point by ID.
    - `update_point(self, point_id, name, x, y, signal_name, notes, group_name, trigger_config, net_name)` — Update an existing probe point.
    - `delete_point(self, point_id)` — Delete a probe point.
    - `save_netlist(self, image_path, original_name, nets)` — Replace the netlist for an image with parsed ``nets`` and return a summary.
    - `get_netlist_summary(self, image_path)` — Return ``{original_name, net_count, node_count, created_at}`` or None.
    - `get_nets(self, image_path)` — Return all nets for an image as ``{name, code, nodes:[{ref,pin,function}]}``.
    - `delete_netlist(self, image_path)` — Delete an image's netlist and its nets/nodes. Returns True if removed.
    - `delete_all_points(self, image_path)` — Delete all probe points for an image. Returns count deleted.
    - `register_image(self, path, original_name, project_id)` — Register an image in the database, optionally scoped to a project.
    - `get_images(self, project_id)` — Get registered images, optionally filtered by project.
    - `get_image_info(self, image_path)` — Get a single image's metadata by its path.
    - `rename_image(self, image_path, new_name)` — Rename an image's display name (original_name) in the database.
    - `delete_image(self, image_path)` — Delete an image and all associated data (points, scans, results, calibrations, voltages).
    - `export_points(self, image_path)` — Export points for an image as JSON.
    - `get_next_point_name(self, image_path)` — Get the next suggested point name (sequential number).
    - `create_scan(self, image_path, scan_type, output_dir, project_id)` — Create a new scan record. Returns the scan ID.
    - `add_scan_result(self, scan_id, point_id, point_name, screenshot_path, waveform_path, plugin_name, extra_files)` — Add a scan result for a probe point.
    - `get_scan_results(self, scan_id)` — Get all results for a scan.
    - `get_scans_for_image(self, image_path)` — Get all scans for an image.
    - `get_results_for_point(self, point_name, image_path)` — Get all scan results for a specific point name across all scans for an image.
    - `get_scan(self, scan_id)` — Get a specific scan by ID.
    - `get_baseline_scan_for_image(self, image_path)` — Get the baseline scan for an image.
    - `set_scan_baseline(self, scan_id)` — Mark a scan as the baseline for its image, clearing any previous baseline.
    - `clear_scan_baseline(self, scan_id)` — Clear a scan's baseline flag.
    - `delete_scan(self, scan_id)` — Delete a scan and its results from the database.
    - `save_calibration_point(self, image_path, point_index, img_x, img_y, phys_x, phys_y)` — Save or update a single calibration point (index 0, 1, or 2).
    - `get_calibration(self, image_path)` — Get calibration points for an image. Returns list of 3 dicts or None.
    - `delete_calibration(self, image_path)` — Delete all calibration points for an image.
    - `create_region_calibration(self, image_path, name, x1, y1, x2, y2)` — Create a named rectangular region (in image %) for an image and return it.
    - `get_region_calibration(self, region_id)` — Return a region calibration (with its anchors and parsed transform), or None.
    - `list_region_calibrations(self, image_path)` — Return all region calibrations for an image, newest first.
    - `save_region_calibration_point(self, region_calibration_id, anchor_name, img_x, img_y, phys_x, phys_y)` — Insert or update a named anchor (image-percent to physical-mm) for a region.
    - `get_region_calibration_points(self, region_calibration_id)` — Return the anchor points recorded for a region calibration.
    - `update_region_calibration_fit(self, region_calibration_id, transform_type, transform_params, fit_status, rms_error, max_error)` — Store a computed transform + fit quality for a region, clearing prior verification.
    - `update_region_calibration_verification(self, region_calibration_id, point_id, error_mm)` — Record a verification result (the probe point checked and its error in mm).
    - `delete_region_calibration(self, region_calibration_id)` — Delete a region calibration and its anchors; return True if one was removed.
    - `save_voltage_reading(self, image_path, point_id, voltage, voltage_min, voltage_max, scan_id)` — Save a voltage reading for a probe point.
    - `get_latest_voltages(self, image_path)` — Get the most recent voltage reading per point for an image.
    - `get_all_voltages(self, image_path)` — Get all voltage readings for an image, ordered by point then timestamp.
    - `get_voltages_for_scan(self, scan_id)` — Get the most recent voltage reading per point for a specific scan.
    - `save_protocol_detection(self, scan_result_id, protocol, parameters, confidence)` — Save a protocol detection result. Returns the detection ID.
    - `clear_protocol_detections_for_scan(self, scan_id)` — Delete all protocol detections for a scan. Returns count deleted.
    - `get_protocol_detections(self, scan_result_id)` — Get protocol detections for a single scan result.
    - `get_protocol_detections_for_scan(self, scan_id)` — Get all protocol detections for a scan (joins with scan_results).
    - `search_scan_points(self, project_id, image_path, point_query, signal_query, protocol, voltage_min, voltage_max, limit)` — Search scan history across projects/images and return one row per point per scan.
    - `upsert_report(self, scan_id, image_path, file_path, report_format)` — Insert or update a generated report record for a scan/format.
    - `save_report(self, scan_id, image_path, file_path, report_format)` — Save a generated report record. Returns the report ID.
    - `get_reports_for_scan(self, scan_id)` — Get all reports for a scan, most recent first.
    - `get_reports(self, image_path)` — Get all reports for an image, most recent first.
    - `get_report_sets(self, image_path)` — Get all reports for an image grouped by scan.
    - `get_report(self, report_id)` — Get a single report by ID.
    - `delete_reports_for_scan(self, scan_id)` — Delete all report records for a scan and return the deleted rows.
    - `delete_report(self, report_id)` — Delete a report record (does not delete the file).
    - `save_scan_template(self, name, plugins, hooks, power_timeout, trigger_config)` — Save or update a scan template. Returns template ID.
    - `get_scan_templates(self)` — List all scan templates.
    - `delete_scan_template(self, template_id)` — Delete a scan template.
    - `set_criteria(self, image_path, point_id, voltage_min, voltage_max, expected_protocol, expected_signal_type, custom_label)` — Set or update pass/fail criteria for a probe point. Returns criteria ID.
    - `get_criteria(self, image_path)` — Get all pass/fail criteria for an image.
    - `delete_criteria(self, criteria_id)` — Delete a pass/fail criteria entry.
    - `evaluate_scan(self, scan_id)` — Evaluate a scan against pass/fail criteria.

## `app.runtime.probe_scan`

`app/runtime/probe_scan.py`

Scan session orchestration.

- **`def load_config()`** — Load instrument configuration from config.json.
- **`class ScanSession`** — Manages instrument connections for a scan session.
    - `__init__(self, plugin_names, output_dir, timeout, image_path, hook_names, project_id)` — Set up a scan session for the selected plugins/hooks and output directory.
    - `probe_point(self, point, phase_callback)` — Probe a single point and return the result.
    - `get_status(self)` — Return connection status for all instruments in this session.
    - `cancel(self)` — Cancel the scan session safely (power off, retract probe).
    - `close(self)` — Clean up instrument connections.
- **`def start_scan_session(plugin_names, output_dir, timeout, image_path, hook_names, project_id)`** — Start a new scan session.
- **`def probe_single_point(point)`** — Probe a single point using the current scan session.
- **`def cancel_scan_session()`** — Cancel the current scan session (safe power-off and retract).
- **`def end_scan_session()`** — End the current scan session.

## `app.runtime.scopectl`

`app/runtime/scopectl.py`

Oscilloscope control over VISA/SCPI (Rigol).

- **`class ScopeControl`** — Connection to a Rigol oscilloscope.
    - `__init__(self, resource_string)` — Connect to the scope at ``resource_string`` and verify identity.
    - `set_single_trigger(self)` — Arm a single-shot trigger (``:SING``).
    - `get_screenshot(self, filepath)` — Capture the scope display as a PNG and write it to ``filepath``.
    - `save_wav(self, filepath)` — Save the current waveform to a WMF file on the instrument.
    - `save_csv(self, filepath)` — Save the current waveform to a CSV file on the instrument.
    - `channel_display(self, channel, status)` — Turn a channel's display on (``status`` truthy) or off.
    - `extract_logic(self, channels, output_path)` — Export raw bytes for each digital (``D``) channel to ``output_path``.
    - `extract_waveform(self, channels, output_path)` — Export raw bytes for each analog (``CHAN``) channel to ``output_path``.
    - `get_waveform_preamble(self, channel)` — Query the Rigol waveform preamble for a channel.
    - `extract_waveform_to_file(self, channel, filepath)` — Extract waveform from a single channel to a specific file.
    - `get_channel_statistics(self, channel)` — Set the measurement source to the given analog channel.
    - `set_statistic_display(self, status)` — Enable (``status`` truthy) or disable the measurement statistics display.
    - `get_stats_from_capture(self, channel)` — Return measurement statistics for a channel. Placeholder — not yet implemented.
    - `get_average_voltages(self, channel)` — Return average voltage measurements for a channel. Placeholder — not yet implemented.
    - `get_trigger_status(self)` — Query whether the scope has triggered.
    - `force_trigger(self)` — Force an immediate trigger event.
    - `get_trigger_setup(self, channel)` — Query current edge trigger settings and return as a dict.
    - `set_trigger_channel(self, channel)` — Set edge trigger source channel. channel: 1-4.
    - `set_trigger_threshold(self, voltage)` — Set edge trigger level in volts.
    - `set_trigger_edge(self, edge)` — Set edge trigger slope. edge: 'rising', 'falling', or 'either'.
    - `set_trigger_type(self, trig_type)` — Set trigger mode. trig_type: 'edge', etc.
    - `set_trigger_coupling(self, coupling)` — Set trigger coupling. coupling: 'dc', 'ac', 'lfr', 'hfr'.
    - `configure_trigger(self, config)` — Apply a full edge trigger configuration from a dict.

## `app.runtime.powerctl`

`app/runtime/powerctl.py`

Power-supply control over VISA/SCPI.

- **`class PowerControl`** — Connection to a programmable power supply.
    - `__init__(self, resource_string)` — Connect to the power supply at ``resource_string``.
    - `set_voltage(self, voltage, channel)` — Set the output voltage (volts) for ``channel``.
    - `set_current(self, current, channel)` — Set the current limit (amps) for ``channel``.
    - `get_current(self, channel)` — Return the configured current limit for ``channel``.
    - `get_voltage(self, channel)` — Return the configured output voltage for ``channel``.
    - `turn_output_off(self, channel)` — Disable the supply output.
    - `turn_output_on(self, channel)` — Enable the supply output.
    - `measure_current(self, channel)` — Measure the actual current being drawn on ``channel``.
    - `measure_voltage(self, channel)` — Measure the actual output voltage on ``channel``.

## `app.runtime.motionctl`

`app/runtime/motionctl.py`

GRBL XYZ-table control over serial.

- **`class MotionControl`** — GRBL-based XYZ table controller over serial.
    - `__init__(self, port, baud_rate)` — Open the serial connection to the GRBL controller on ``port``.
    - `home(self)` — Home all axes ($H).
    - `move_to(self, x, y, z, feed_rate)` — Absolute move to the given coordinates. Waits for completion.
    - `jog(self, axis, distance, feed_rate)` — Incremental jog along a single axis.
    - `get_position(self)` — Return current machine position as {x, y, z}.
    - `set_zero(self)` — Set current position as the work coordinate origin.
    - `unlock(self)` — Clear GRBL alarm lock.
    - `close(self)` — Close the serial connection.

## `app.runtime.calibration`

`app/runtime/calibration.py`

Affine transform calibration for mapping image coordinates (%) to physical coordinates (mm).

- **`def compute_affine(cal_points)`** — Compute affine transform matrix from 3 calibration point pairs.
- **`def fit_affine(cal_points)`** — Fit an affine transform from 3 or more point correspondences.
- **`def image_to_physical(affine, img_x, img_y)`** — Convert image % coordinates to physical mm coordinates.
- **`def point_in_box(img_x, img_y, x1, y1, x2, y2)`** — Return whether an image-space point lies inside a rectangular region.
- **`def region_corner_points(region)`** — Return the four image-space corners of a rectangular region.

## `app.runtime.sigrok_utils`

`app/runtime/sigrok_utils.py`

Sigrok session file (.sr) utilities.

- **`def format_sample_rate(rate_hz)`** — Format a sample rate in Hz to a human-readable sigrok string.
- **`def raw_to_volts(raw_bytes, preamble)`** — Convert raw 8-bit ADC bytes to float voltage list using Rigol preamble.
- **`def raw_to_volts_manual(raw_bytes, volts_per_div, probe_atten)`** — Best-effort voltage conversion without preamble data.
- **`def find_preamble_for_bin(bin_path)`** — Look for a preamble JSON sidecar next to a .bin file.
- **`def write_sr(output_path, voltage_samples, sample_rate, channel_name)`** — Write a sigrok .sr session file with one analog channel.

## `protocol_detect`

`protocol_detect.py`

Protocol detection and waveform-analysis helpers.

- **`def parse_sigrok_csv(filepath)`** — Parse a sigrok/saleae CSV file.
- **`def find_edges(timestamps, values)`** — Find all rising and falling edges in a digital signal.
- **`def detect_uart(timestamps, values)`** — Detect UART protocol from a single-channel digital waveform.
- **`def classify_signal(timestamps, values)`** — Classify a single-channel capture into a signal type category.
- **`def group_voltage_domains(voltage_readings)`** — Cluster probe point voltage readings into standard voltage domains.
- **`def detect_uart_binary(filepath)`** — Detect UART in a raw oscilloscope binary capture (.bin file).
- **`def detect_emmc_binary(filepath)`** — Detect eMMC bus signals in a raw oscilloscope binary capture.
- **`def analyze_binary_waveform(filepath)`** — Analyze a binary waveform file (1 byte per sample, 0-255).
- **`def analyze_scan_result(waveform_path, plugin_name)`** — Analyze a scan result's waveform file for protocol detection.

## `plugins.base`

`plugins/base.py`

Scan plugin contract.

- **`class PluginResult`** — Outcome of a successful capture for one probe point.
- **`class PluginError`** — Structured failure from a scan phase.
- **`class ScanPlugin`** — Base class for instrument plugins driven during a scan.
    - `__init__(self, config)` — Receive plugin's config section from config.json instruments.<name>.
    - `prepare(self, point, output_dir)` — Before power-on: arm trigger, configure capture, etc.
    - `capture(self, point, output_dir)` — After power-on + timeout: stop acquisition, wait for capture, etc.
    - `save(self, point, output_dir)` — Export data to files in output_dir. Return paths.
    - `reconnect(self)` — Attempt to re-establish instrument connection. Override if applicable.
    - `close(self)` — Release instrument resources at session end.

## `hooks.base`

`hooks/base.py`

Scan hook contract.

- **`class HookResult`** — Optional result from a hook execution.
- **`class ScanHook`** — Base class for scan lifecycle hooks.
    - `__init__(self, config)` — Initialize the hook. Config comes from config.json hooks.<name>,
    - `before_power_on(self, point, output_dir)` — Called after instruments are prepared, before power supply turns on.
    - `after_capture(self, point, output_dir)` — Called after all plugins have captured data, before power supply turns off.
    - `close(self)` — Release resources when the scan session ends. Default is a no-op.

## `analysis.base`

`analysis/base.py`

Analysis plugin contract.

- **`class AnalysisResult`** — Result from an analysis plugin run on a single scan result.
- **`class AnalysisPlugin`** — Base class for post-scan analysis plugins.
    - `analyze(self, scan_result, output_dir)` — Analyze a single scan result.

## `analysis.report_generator`

`analysis/report_generator.py`

Unified report generator — single Markdown source for both HTML and PDF.

- **`def generate_report_markdown(scan, results, detections, points, voltage_readings, project, image_info, scan_config, evaluation, instrument_info, scan_config_snapshot, criteria, operator, organization, confidentiality, output_format)`** — Generate a complete Markdown report document.
- **`def generate_pdf(markdown_text, reports_dir, scan_id)`** — Convert markdown to PDF via pandoc + eisvogel. Returns path or None.
- **`def save_markdown(markdown_text, reports_dir, scan_id)`** — Persist the source markdown report and return its path.
- **`def generate_html(markdown_text, reports_dir, scan_id)`** — Convert markdown to styled self-contained HTML via pandoc. Returns path or None.
- **`def cleanup_temp_files(reports_dir)`** — Remove temporary overlay, crop, and screenshot files from reports dir.

\newpage

# Appendix: Generation Metadata

| Field | Value |
|---|---|
| Generated | 2026-06-07 01:54 UTC |
| Source commit | `c594124` |
| Endpoints | 102 |
| Plugins / Hooks / Analyzers | 5 / 1 / 4 |
| Database tables | 16 |
