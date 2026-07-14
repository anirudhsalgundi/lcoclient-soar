# download_soar_data.py

A command-line tool for querying and downloading SOAR/GHTS data from the LCO archive. Supports flexible filtering by frame type, observing mode, and target, with three download layout modes including a dedicated `soar_dps` mode for the SOAR DPS reduction pipeline.

---

## Requirements

- `LCO_TOKEN` environment variable set to your LCO API token

```bash
export LCO_TOKEN=your_token_here
```

---

## Usage

```bash
python download_soar_data.py --help
```

** For any of the soar-dps reduction scripts, you can use the following command to download data for a specific time range: **
```bash
python download_soar_data.py --tstart TSTART --tstop TSTOP [OPTIONS]
```

---

## Arguments

### Required

| Argument | Description |
|----------|-------------|
| `--tstart` | Start time in ISO format (e.g. `2026-06-01` or `2026-06-01T00:00:00`) |
| `--tstop` | End time in ISO format (e.g. `2026-06-02` or `2026-06-02T00:00:00`) |

### Filters (all optional)

| Argument | Choices | Default | Description |
|----------|---------|---------|-------------|
| `--obs_mode` | `photometry`, `spectroscopy` | both | Restrict to one observing mode |
| `--frame_type` | `bias`, `flats`, `arcs`, `science`, `standard`, `cals`, `all` | required (except in `soar_dps` mode) | Frame types to download; `cals` expands to bias+flats (+arcs for spectroscopy); `all` expands to everything |
| `--target_name` | any string | all targets | Filter science/standard frames to a specific target |

### Download mode

| Argument | Choices | Default | Description |
|----------|---------|---------|-------------|
| `--download_type` | `structured`, `unstructured`, `soar_dps` | `soar_dps` | Directory layout for downloaded files |
| `--query_only` | flag | off | Print the download table without downloading anything |
| `--dest_path` | any path | `~/Downloads` | Base path for output directory (not used in `soar_dps` mode) |

---

## Download Modes

### `soar_dps` (default)

Tailored for the SOAR DPS reduction pipeline. `--frame_type` is not required and always defaults to `all`.

- **Photometry**: fetches LCO-reduced frames, grouped per target
- **Spectroscopy**: fetches all raw frames, dumped together

```
soar_dps_download_YYYYMMDD_HHMMSS/
    photometry/
        ZTF24abcdefg/
            raw/
                *.fits.fz
        ZTF24hijklmn/
            raw/
                *.fits.fz
    spectroscopy/
        raw/
            *.fits.fz
```

### `structured`

Full directory hierarchy organized by mode, frame type, and target.

```
soar_download_YYYYMMDD_HHMMSS/
    photometry/
        science/
            ZTF24abcdefg/
                *.fits.fz
        cals/
            bias/
                *.fits.fz
            flats/
                *.fits.fz
    spectroscopy/
        science/
            ZTF24abcdefg/
                *.fits.fz
        standard/
            *.fits.fz
        cals/
            bias/
                *.fits.fz
            flats/
                *.fits.fz
            arcs/
                *.fits.fz
```

### `unstructured`

All files dumped into a single flat directory, regardless of mode or type.

```
soar_download_YYYYMMDD_HHMMSS/
    *.fits.fz
```

---

## Frame Type Expansions

| Shortcut | Photometry expands to | Spectroscopy expands to |
|----------|-----------------------|-------------------------|
| `cals`   | `bias`, `flats`       | `bias`, `flats`, `arcs` |
| `all`    | `bias`, `flats`, `science` | `bias`, `flats`, `arcs`, `science`, `standard` |

Note: `arcs` and `standard` are spectroscopy-only and are silently dropped when `--obs_mode photometry` is set.

---

## Examples

### Query only — see what is available before downloading

```bash
python download_soar_data.py \
    --tstart 2026-06-23 \
    --tstop 2026-06-24 \
    --query_only
```

### Default soar_dps mode (no --frame_type needed)

```bash
python download_soar_data.py \
    --tstart 2026-06-23 \
    --tstop 2026-06-24
```

### soar_dps mode for a specific target

```bash
python download_soar_data.py \
    --tstart 2026-06-23 \
    --tstop 2026-06-24 \
    --target_name ZTF24abcdefg
```

### Structured download of all frames

```bash
python download_soar_data.py \
    --tstart 2026-06-23 \
    --tstop 2026-06-24 \
    --frame_type all \
    --download_type structured
```

### Structured download of calibrations only

```bash
python download_soar_data.py \
    --tstart 2026-06-23 \
    --tstop 2026-06-24 \
    --frame_type cals \
    --download_type structured
```

### Structured download of science frames for a specific target

```bash
python download_soar_data.py \
    --tstart 2026-06-23 \
    --tstop 2026-06-24 \
    --frame_type science \
    --target_name ZTF24abcdefg \
    --download_type structured
```

### Unstructured download of spectroscopy only

```bash
python download_soar_data.py \
    --tstart 2026-06-23 \
    --tstop 2026-06-24 \
    --frame_type all \
    --obs_mode spectroscopy \
    --download_type unstructured
```

### Download to a custom directory

```bash
python download_soar_data.py \
    --tstart 2026-06-23 \
    --tstop 2026-06-24 \
    --frame_type all \
    --download_type structured \
    --dest_path /path/to/my/data
```

---

## Notes

- The download summary table is always printed before files are downloaded, showing frame counts per type, target, and mode.
- In `soar_dps` mode, photometry fetches **LCO-reduced** frames (identified by `reduction_level != 0`). Spectroscopy fetches raw frames.
- Passing `--frame_type` with anything other than `all` in `soar_dps` mode raises an error.
- If a file already exists at the output path it is skipped.
- Time windows are automatically chunked into 1-day slices to avoid large API responses.
- If `--tstop` is in the future it is automatically adjusted to the current time.
- If no calibration frames are found in the requested time range, the client automatically expands the search window by ±1 day at a time up to a maximum of 7 days.