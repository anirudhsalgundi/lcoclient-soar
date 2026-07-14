# soarpy

A Python client and CLI for querying and downloading SOAR/Goodman (GHTS) frames from the
[Las Cumbres Observatory (LCO)](https://lco.global/) archive, tailored for the SOAR DPS
(Data Processing System) reduction workflow.

`soarpy` handles:

- Authenticating against the LCO API
- Querying the archive for frames within a time range
- Classifying frames into photometric/spectroscopic bias, flat, arc, science, and standard-star
  categories
- Automatically expanding the search window when calibration frames aren't found in the
  requested range
- Downloading frames to disk in one of several directory layouts

---

## Table of contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Package layout](#package-layout)
- [CLI usage (`soar-download`)](#cli-usage-soar-download)
- [Python API](#python-api)
- [Frame classification model](#frame-classification-model)
- [Downstream: PypeIt reduction](#downstream-pypeit-reduction)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## Installation

This project uses [uv](https://docs.astral.sh/uv/) and a standard `pyproject.toml`
(build backend: hatchling). Requires Python 3.13+.

```bash
# clone, then from the repo root:
uv sync
```

This creates a `.venv` and installs `soarpy` in editable mode along with its dependencies
(`astropy`, `requests`, `rich`).

Without `uv`, a plain venv + pip also works:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Once installed, the `soar-download` console script is available on your `PATH` inside the
virtual environment, and `import soarpy` works from anywhere in that environment.

---

## Configuration

The client authenticates against the LCO API using a personal API token.

```bash
export LCO_TOKEN=your_token_here
```

Get your token from your [LCO account profile](https://observe.lco.global/accounts/profile/).
You can also pass the token directly when constructing the client instead of relying on the
environment variable (see [Python API](#python-api)).

---

## Package layout

```
soarpy/
├── __init__.py       # exposes soarpy.LCOClient and soarpy.lco_client
├── lco_client.py      # LCOClient: archive auth, querying, frame classification
├── download.py        # soar-download CLI (argparse entry point: main())
├── utils.py            # misc helpers (e.g. proposal/account stats)
├── logger.py            # shared Rich-based logging setup
├── config/
│   └── sensfunc.par      # default PypeIt sensitivity-function config, reused across reductions
└── data/
    └── observe.lco.global.json   # reference map of LCO observe-portal API endpoints

notebooks/
└── download_data.ipynb  # exploratory notebook exercising LCOClient end-to-end

docs/
└── pypeit_manual_reduction_guide.MD  # manual PypeIt reduction walkthrough (downstream of soarpy)
```

---

## CLI usage (`soar-download`)

```bash
soar-download --tstart TSTART --tstop TSTOP [OPTIONS]
```

(You can also run it as `python -m soarpy.download` or `python soarpy/download.py` if not
installed as a script.)

### Required arguments

| Argument   | Description |
|------------|-------------|
| `--tstart` | Start time, ISO format (e.g. `2026-06-01` or `2026-06-01T00:00:00`) |
| `--tstop`  | End time, ISO format (e.g. `2026-06-02` or `2026-06-02T00:00:00`) |

### Filters (optional)

| Argument        | Choices                                                        | Default | Description |
|-----------------|-----------------------------------------------------------------|---------|-------------|
| `--obs_mode`    | `photometry`, `spectroscopy`                                    | both    | Restrict to one observing mode |
| `--frame_type`  | `bias`, `flats`, `arcs`, `science`, `standard`, `cals`, `all`    | required (except in `soar_dps` mode) | Frame types to download. `cals` expands to bias+flats (+arcs for spectroscopy). `all` expands to everything. Comma- or space-separated. |
| `--target_name` | any string                                                       | all targets | Filter science/standard frames to a specific target |

### Download mode

| Argument          | Choices                                    | Default    | Description |
|-------------------|----------------------------------------------|------------|-------------|
| `--download_type` | `structured`, `unstructured`, `soar_dps`      | `soar_dps` | Directory layout for downloaded files |
| `--query_only`     | flag                                          | off        | Print the download table without downloading anything |
| `--dest_path`      | any path                                       | `~/Downloads` | Base path for the output directory |
| `--verify_bands` / `--no_verify_bands` | flag | on (verify) | In `soar_dps` photometry mode, fall back to raw science + cals for any band missing LCO-reduced data |

### Download layouts

**`soar_dps` (default)** — tailored for the SOAR DPS reduction pipeline. `--frame_type` is not
required and always defaults to `all`. Photometry fetches LCO-reduced frames grouped per
target; spectroscopy fetches all raw frames.

```
soar_data_download_<DDMMYYHHMMSS>/
    photometry/
        ZTF24abcdefg/
            raw/
                *.fits.fz
    spectroscopy/
        raw/
            *.fits.fz
```

**`structured`** — full hierarchy organized by mode, frame type, and target.

```
soar_data_download_<DDMMYYHHMMSS>/
    photometry/
        science/
            ZTF24abcdefg/
                *.fits.fz
        cals/
            bias/
            flats/
    spectroscopy/
        science/
            ZTF24abcdefg/
        standard/
        cals/
            bias/
            flats/
            arcs/
```

**`unstructured`** — everything dumped into one flat directory.

```
soar_data_download_<DDMMYYHHMMSS>/
    *.fits.fz
```

### Frame type expansions

| Shortcut | Photometry expands to      | Spectroscopy expands to             |
|----------|------------------------------|--------------------------------------|
| `cals`   | `bias`, `flats`               | `bias`, `flats`, `arcs`              |
| `all`    | `bias`, `flats`, `science`    | `bias`, `flats`, `arcs`, `science`, `standard` |

`arcs` and `standard` are spectroscopy-only and are silently dropped when
`--obs_mode photometry` is set.

### Examples

Query only, no download:

```bash
soar-download --tstart 2026-06-23 --tstop 2026-06-24 --query_only
```

Default `soar_dps` mode:

```bash
soar-download --tstart 2026-06-23 --tstop 2026-06-24
```

`soar_dps` mode for one target:

```bash
soar-download --tstart 2026-06-23 --tstop 2026-06-24 --target_name ZTF24abcdefg
```

Structured download of everything:

```bash
soar-download --tstart 2026-06-23 --tstop 2026-06-24 --frame_type all --download_type structured
```

Structured, calibrations only:

```bash
soar-download --tstart 2026-06-23 --tstop 2026-06-24 --frame_type cals --download_type structured
```

Structured science frames for one target:

```bash
soar-download \
    --tstart 2026-06-23 --tstop 2026-06-24 \
    --frame_type science --target_name ZTF24abcdefg --download_type structured
```

Unstructured, spectroscopy only:

```bash
soar-download \
    --tstart 2026-06-23 --tstop 2026-06-24 \
    --frame_type all --obs_mode spectroscopy --download_type unstructured
```

Custom destination:

```bash
soar-download \
    --tstart 2026-06-23 --tstop 2026-06-24 \
    --frame_type all --download_type structured --dest_path /path/to/my/data
```

### Notes

- A Rich-rendered summary table (frame counts per type/target/mode) is always printed before
  files are downloaded.
- In `soar_dps` mode, photometry fetches **LCO-reduced** frames (`reduction_level != 0`);
  spectroscopy fetches raw frames.
- Passing `--frame_type` other than `all` with `--download_type soar_dps` raises an error.
- Existing files at the destination path are skipped (idempotent re-runs).
- Time windows are automatically chunked into 1-day slices to keep API responses small.
- If `--tstop` is in the future, it's clamped to the current time.
- If no calibration frames are found in the requested range, the client expands the search
  window by ±1 day at a time, up to ±7 days, before giving up.

---

## Python API

```python
import os
from soarpy import LCOClient

client = LCOClient(api_token=os.environ["LCO_TOKEN"])  # or omit to read LCO_TOKEN automatically

frames = client.get_frames("2026-06-23T00:00:00", "2026-06-24T00:00:00")

science = client.get_science_frames(frames, mode="photometry")
bias, flats = client.get_calibration_frames(frames, mode="photometry",
                                             tstart="2026-06-23", tstop="2026-06-24")
bias, flats, arcs = client.get_calibration_frames(frames, mode="spectroscopy",
                                                   tstart="2026-06-23", tstop="2026-06-24")

reduced = client.get_lco_reduced_frames(frames, mode="photometry")
band = client.get_frame_band(frames[0])  # e.g. 'gp', 'rp', or 'unknown'
```

### `LCOClient`

| Method | Description |
|--------|-------------|
| `__init__(api_token=None)` | Authenticates immediately against the LCO profile endpoint. Reads `LCO_TOKEN` from the environment if `api_token` isn't given. Raises `ValueError` if no token is available or authentication fails. |
| `get_frames(tstart, tstop)` | Queries the archive frames endpoint across the whole range, chunked into 1-day windows, following pagination. Returns a flat list of frame metadata dicts. |
| `get_science_frames(frames, mode)` | Filters science frames for `"photometry"` or `"spectroscopy"`. |
| `get_calibration_frames(frames, mode, tstart, tstop)` | Returns `(bias, flats)` for photometry, `(bias, flats, arcs)` for spectroscopy. Falls back to `_expand_time_range_until_frames_found` for any empty category. |
| `get_lco_reduced_frames(frames, mode)` | Frames with `reduction_level != 0` for the given mode. |
| `get_frame_band(frame)` (staticmethod) | Returns `primary_optical_element`, falling back to `FILTER`, or `"unknown"`. |

Constants controlling frame classification live in `soarpy.lco_client.Constants`
(`LCO_FRAME_URL`, `SOAR_TELESCOPE_ID`, `QUERY_LIMIT`, `OBSMODE_INSTRUMENTS`,
`REQUIRED_CCD_BINNING`).

---

## Frame classification model

Frames are classified using `instrument_id`, `configuration_type`, `proposal_id`, `RLEVEL`,
and, for some spectroscopic types, substring checks against `filename`/`target_name`:

| Frame type | Mode | Key conditions |
|------------|------|-----------------|
| Photometric bias | photometry | instrument in `{ghts_blue_imager, ghts_red_imager}`, `proposal_id == "calibrate"`, `configuration_type == "bias"`, `RLEVEL == 0` |
| Photometric flat | photometry | as above with `configuration_type == "lampflat"` |
| Photometric science | photometry | `proposal_id != "calibrate"`, `configuration_type == "expose"`, `RLEVEL == 0` |
| Spectroscopic bias | spectroscopy | `configuration_type == "bias"`, `RLEVEL == 0`, `"2x2"` in `target_name` |
| Spectroscopic flat | spectroscopy | instrument in `{ghts_blue, ghts_red}`, `configuration_type == "lampflat"`, `RLEVEL == 0`, `"2x2"` in filename, `"slit"` not in filename |
| Spectroscopic arc | spectroscopy | `configuration_type == "arc"`, `RLEVEL == 0`, `proposal_id != "calibrate"` |
| Spectroscopic science | spectroscopy | `configuration_type == "spectrum"`, `RLEVEL == 0`, `proposal_id != "calibrate"` |
| Standard star (spectroscopic) | spectroscopy | `"Calibration-Star"` in `filename`, `proposal_id == "calibrate"`, `RLEVEL == 0` |
| LCO-reduced | either | `reduction_level != 0`, instrument matches the mode's instrument set |

If any calibration category comes back empty for the requested window, the client widens the
search by ±1, ±2, ... up to ±7 days around `[tstart, tstop]` until frames are found or the
limit is hit (see `_expand_time_range_until_frames_found`).

---

## Downstream: PypeIt reduction

`soarpy/config/sensfunc.par` is a reusable default PypeIt sensitivity-function configuration,
intended to be copied into a fresh reduction directory alongside frames downloaded by this
tool. See [`docs/pypeit_manual_reduction_guide.MD`](docs/pypeit_manual_reduction_guide.MD) for
the full manual walkthrough of a PypeIt-based spectroscopic reduction using data fetched with
`soar-download`.

---

## Development

```bash
uv sync                 # install soarpy + deps into .venv
uv run soar-download --help
uv run python -c "from soarpy import LCOClient"
```

There is no automated test suite yet; `notebooks/download_data.ipynb` is an exploratory notebook
used to exercise `LCOClient` interactively against the live LCO API (requires `LCO_TOKEN`).

---

## Troubleshooting

- **`ValueError: LCO API token is required.`** — set `LCO_TOKEN` or pass `api_token=` explicitly.
- **`Authentication failed: 401 ...`** — token is invalid, expired, or lacks archive access.
- **Empty download plan / 0 frames** — double check `--tstart`/`--tstop` bracket real
  observations, and that `--obs_mode`/`--target_name` aren't filtering everything out; try
  `--query_only` first to inspect what the archive returns before downloading.
- **Calibration frames missing** — the client auto-expands the search window up to ±7 days;
  if still empty, calibrations genuinely weren't taken near that time.
