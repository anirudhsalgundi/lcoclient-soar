#filters
#obs mode p,s
#p[cals, science[target]] if target, if not p[cals, science]
#s[cals, science[target], standard] if target, if not s[cals, science, standard]
# if bias and p, download p[cals[bias]]
# if flat and p, download p[cals[flat]]
# if bias and s, download s[cals[bias]]
# if flat and s, download s[cals[flat]]
# if arc and s, download s[cals[arc]]
# if science and p, download p[science[target]] if target, if not p[science]
# if science and s, download s[science[target]] if target, if not s[science]
# if science and p and target, download p[science[target]]
# if science and s and target, download s[science[target]]
# if standard and s, download s[standard]


#!/usr/bin/env python
"""CLI tool for downloading SOAR/Goodman frames from the LCO archive."""

import argparse
import os
import subprocess
import sys
from datetime import datetime

from soarpy import lco_client

from rich.table import Table
from rich.console import Console

from rich import box
from soarpy.logger import get_logger, setup_logging, log_download
logger = get_logger(__name__)


console = Console()

# frame types that only exist in spectroscopy
SPECTROSCOPY_ONLY = {"arcs", "standard"}

# what --cals expands to per mode
CALS_EXPANSION = {
    "photometry":    {"bias", "flats"},
    "spectroscopy":  {"bias", "flats", "arcs"},
}

# what --all expands to per mode
ALL_EXPANSION = {
    "photometry":    {"bias", "flats", "science"},
    "spectroscopy":  {"bias", "flats", "arcs", "science", "standard"},
}

VALID_FRAME_TYPES = {"bias", "flats", "arcs", "science", "standard", "cals", "all"}


def parse_frame_types(raw: list[str]) -> set[str]:
    """Parse --frame_type values, supporting both space-separated and comma-separated."""
    frame_types = set()
    for item in raw:
        for part in item.split(","):
            part = part.strip().lower()
            if part:
                frame_types.add(part)
    return frame_types


def validate_args(frame_types: set[str], obs_modes: list[str]):
    """Validate frame_type and obs_mode combinations. Exit on invalid."""
    invalid = frame_types - VALID_FRAME_TYPES
    if invalid:
        logger.error(f"Invalid frame type(s): {', '.join(invalid)}")
        console.print(f"Valid options: {', '.join(sorted(VALID_FRAME_TYPES))}")
        sys.exit(1)

    # check spectroscopy-only types against obs_mode
    if obs_modes == ["photometry"]:
        bad = frame_types & SPECTROSCOPY_ONLY
        if bad:
            logger.error(
                f"Invalid combination: {', '.join(bad)} "
                f"only exist in spectroscopy, but --obs_mode is photometry."
            )
            sys.exit(1)


def expand_frame_types(frame_types: set[str], mode: str) -> set[str]:
    """Expand 'cals' and 'all' into concrete frame types for a given mode."""
    expanded = set()
    for ft in frame_types:
        if ft == "cals":
            expanded |= CALS_EXPANSION[mode]
        elif ft == "all":
            expanded |= ALL_EXPANSION[mode]
        else:
            expanded.add(ft)
    return expanded


def resolve_frame_types_for_mode(frame_types: set[str], mode: str) -> set[str]:
    """Expand shortcuts and drop frame types that don't apply to this mode."""
    expanded = expand_frame_types(frame_types, mode)
    if mode == "photometry":
        expanded -= SPECTROSCOPY_ONLY
    return expanded


def make_output_dirs(base, obsmode, frame_type, target_name=None):
    """Build and create the output directory path."""
    if frame_type == "science" and target_name:
        path = os.path.join(base, obsmode, "science", target_name)
    elif frame_type == "science":
        path = os.path.join(base, obsmode, "science")
    elif frame_type == "standard":
        path = os.path.join(base, obsmode, "standard")
    else:
        path = os.path.join(base, obsmode, "cals", frame_type)
    os.makedirs(path, exist_ok=True)
    return path


def download_frames(frames, dest, offset=0, total=None):
    """Download a list of frames to dest, skipping files that already exist."""
    dest = os.path.abspath(dest)
    if total is None:
        total = len(frames)

    for n, frame in enumerate(frames, start=1):
        url = frame["url"]
        filename = frame.get("filename")
        filepath = os.path.join(dest, filename)

        if os.path.exists(filepath):
            logger.info(f"Skipping (exists): {filename}")
            continue

        try:
            log_download(offset + n, total, filename, dest)
            subprocess.run(
                            ["curl", "-#", "-o", filepath, url],
                            check=True,
                        )
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to download {filename}: {e}")


def print_download_table(download_plan: list[dict], query_only: bool = False):
    """Print a Rich table summarizing the download plan."""
    title = "SOAR Download Query" if query_only else "SOAR Download Plan"
    table = Table(title=title, box=box.ROUNDED, show_header=True, header_style="bold cyan")

    table.add_column("Frame Type",   style="green",   justify="center")
    table.add_column("Target Name(s)", style="yellow", justify="center")
    table.add_column("Obs Mode",     style="magenta", justify="center")
    table.add_column("# Frames",     style="white",   justify="right")

    # group by frame_type, then by obsmode
    from collections import OrderedDict
    grouped = OrderedDict()
    for entry in download_plan:
        ft = entry["frame_type"]
        ft = "standard\n(arc + science)" if ft == "standard" else ft
        mode = entry["obsmode"]
        key = (ft, mode)
        if key not in grouped:
            grouped[key] = {"targets": [], "count": 0}
        if entry["target_name"] != "-":
            grouped[key]["targets"].append(entry["target_name"])
        grouped[key]["count"] += entry["count"]

    prev_ft = None
    for (ft, mode), info in grouped.items():
        if prev_ft is not None and ft != prev_ft:
            table.add_section()

        if info["targets"]:
            # 2 targets per line
            pairs = [info["targets"][i:i+2] for i in range(0, len(info["targets"]), 2)]
            targets = "\n".join(", ".join(pair) for pair in pairs)
        else:
            targets = "-"

        table.add_row(ft, targets, mode, str(info["count"]))
        prev_ft = ft

    console.print(table)

    total = sum(e["count"] for e in download_plan)
    console.print(f"[bold]Total frames:[/bold] {total}")

    if query_only:
        console.print("[yellow]Query-only mode — no files downloaded.[/yellow]")

def fetch_frames_by_type(client, frames, mode, frame_type, tstart, tstop, target_name=None):
    """
    Given a mode and a concrete frame type, return the matching frames.
    Handles the calibration expansion fallback via get_calibration_frames.
    """
    if frame_type == "bias":
        result = client.get_calibration_frames(frames, mode, tstart, tstop)
        return result[0]  # bias is always first

    elif frame_type == "flats":
        result = client.get_calibration_frames(frames, mode, tstart, tstop)
        return result[1]  # flats is always second

    elif frame_type == "arcs":
        # spectroscopy only, arcs is third element
        result = client.get_calibration_frames(frames, mode, tstart, tstop)
        return result[2]

    elif frame_type == "science":
        science = client.get_science_frames(frames, mode)
        if mode == "spectroscopy":
            arcs = client._get_spectroscopic_arc_frames(frames)
        if target_name:
            science = [f for f in science if f.get("target_name") == target_name]
        return science

    #FIXME: for now, standard, will put in both the science and arcs
    elif frame_type == "standard":
        return client._get_standard_star_spectroscopic_frames(frames)

    return []


def run(args):
    client = lco_client.LCOClient()
    timestamp = datetime.now().strftime("%d%m%y%H%M%S")

    # determine obs modes
    obs_modes = [args.obs_mode] if args.obs_mode else ["photometry", "spectroscopy"]

    # soar_dps always uses --frame_type all; set it if omitted, reject if something else
    if args.download_type == "soar_dps":
        if args.frame_type is None:
            frame_types = {"all"}
        else:
            frame_types = parse_frame_types(args.frame_type)
            if frame_types != {"all"}:
                logger.error("--download_type soar_dps requires --frame_type all (or omit it)")
                sys.exit(1)
    else:
        if args.frame_type is None:
            logger.error("--frame_type is required for structured/unstructured downloads")
            sys.exit(1)
        frame_types = parse_frame_types(args.frame_type)

    validate_args(frame_types, obs_modes)

    # base destination path (homogenized: always rooted at --dest_path, default ~/Downloads)
    dest_root = os.path.expanduser(args.dest_path)
    base = dest_root if args.dest_path else os.path.join(dest_root, f"soar_data_download_{timestamp}")

    # fetch all frames for the time range once
    frames = client.get_frames(args.tstart, args.tstop)

    download_plan = []
    download_queue = []  # list of (frames_list, dest_path)

    # --- soar_dps mode: different fetch + layout strategy ---
    logger.info(f"Download type: {args.download_type}")
    logger.info(f"Obs modes: {', '.join(obs_modes)}")
    logger.info(f"Frame types: {', '.join(sorted(frame_types))}")
    logger.info(f"Download destination base: {base}")
    if args.download_type == "soar_dps":
        for mode in obs_modes:
            if mode == "photometry":
                reduced = client.get_lco_reduced_frames(frames, "photometry")
                raw_science = client.get_science_frames(frames, "photometry")

                if args.target_name:
                    reduced = [f for f in reduced if f.get("target_name") == args.target_name]
                    raw_science = [f for f in raw_science if f.get("target_name") == args.target_name]
                    download_plan.append({"obsmode": mode, "frame_type": "lco_reduced", "target_name": args.target_name, "count": len(reduced)})
                    if reduced:
                        dest = os.path.join(base, "photometry", args.target_name, "raw")
                        download_queue.append((reduced, dest))
                    targets_raw = {args.target_name: raw_science}
                    targets_reduced = {args.target_name: reduced}
                else:
                    targets_reduced = {}
                    for f in reduced:
                        tname = f.get("target_name", "unknown")
                        targets_reduced.setdefault(tname, []).append(f)

                    targets_raw = {}
                    for f in raw_science:
                        tname = f.get("target_name", "unknown")
                        targets_raw.setdefault(tname, []).append(f)

                    for tname, tframes in sorted(targets_reduced.items()):
                        download_plan.append({"obsmode": mode, "frame_type": "lco_reduced", "target_name": tname, "count": len(tframes)})
                        if tframes:
                            dest = os.path.join(base, "photometry", tname, "raw")
                            download_queue.append((tframes, dest))

                if args.verify_bands:
                    missing_any = False
                    for tname, raw_frames in sorted(targets_raw.items()):
                        reduced_bands = {client.get_frame_band(f) for f in targets_reduced.get(tname, [])}
                        raw_bands = {client.get_frame_band(f) for f in raw_frames}
                        missing_bands = raw_bands - reduced_bands
                        if not missing_bands:
                            continue

                        missing_any = True
                        missing_raw_frames = [f for f in raw_frames if client.get_frame_band(f) in missing_bands]
                        logger.warning(
                            f"Target {tname}: no LCO-reduced data for band(s) "
                            f"{', '.join(sorted(missing_bands))}. Falling back to raw science frames."
                        )
                        download_plan.append({"obsmode": mode, "frame_type": "raw (missing bands)", "target_name": tname, "count": len(missing_raw_frames)})
                        dest = os.path.join(base, "photometry", tname, "raw")
                        download_queue.append((missing_raw_frames, dest))

                    if missing_any:
                        bias, flats = client.get_calibration_frames(frames, "photometry", args.tstart, args.tstop)
                        for cal_name, cal_frames in (("bias", bias), ("flats", flats)):
                            if cal_frames:
                                download_plan.append({"obsmode": mode, "frame_type": cal_name, "target_name": "-", "count": len(cal_frames)})
                                dest = os.path.join(base, "photometry", "cals", cal_name)
                                download_queue.append((cal_frames, dest))

            elif mode == "spectroscopy":
                resolved = resolve_frame_types_for_mode(frame_types, mode)

                for ft in sorted(resolved):
                    if ft in ("science", "standard"):
                        matched = fetch_frames_by_type(client, frames, mode, ft, args.tstart, args.tstop, args.target_name)

                        if args.target_name:
                            download_plan.append({"obsmode": mode, "frame_type": ft, "target_name": args.target_name, "count": len(matched)})
                        else:
                            targets = {}
                            for f in matched:
                                tname = f.get("target_name", "unknown")
                                targets.setdefault(tname, []).append(f)
                            for tname, tframes in sorted(targets.items()):
                                download_plan.append({"obsmode": mode, "frame_type": ft, "target_name": tname, "count": len(tframes)})

                    else:
                        matched = fetch_frames_by_type(client, frames, mode, ft, args.tstart, args.tstop)
                        download_plan.append({"obsmode": mode, "frame_type": ft, "target_name": "-", "count": len(matched)})

                    if matched:
                        dest = os.path.join(base, "spectroscopy", "raw")
                        download_queue.append((matched, dest))

    # --- structured / unstructured modes ---
    else:
        def resolve_dest(mode, ft, target=None):
            if args.download_type == "unstructured":
                os.makedirs(base, exist_ok=True)
                return base
            return make_output_dirs(base, mode, ft, target)

        for mode in obs_modes:
            resolved = resolve_frame_types_for_mode(frame_types, mode)

            for ft in sorted(resolved):
                if ft in ("science", "standard"):
                    science = fetch_frames_by_type(client, frames, mode, ft, args.tstart, args.tstop, args.target_name)

                    if args.target_name:
                        download_plan.append({"obsmode": mode, "frame_type": ft, "target_name": args.target_name, "count": len(science)})
                        if science:
                            dest = resolve_dest(mode, ft, args.target_name)
                            download_queue.append((science, dest))
                    else:
                        targets = {}
                        for f in science:
                            tname = f.get("target_name", "unknown")
                            targets.setdefault(tname, []).append(f)

                        for tname, tframes in sorted(targets.items()):
                            download_plan.append({"obsmode": mode, "frame_type": ft, "target_name": tname, "count": len(tframes)})
                            if tframes:
                                dest = resolve_dest(mode, ft, tname)
                                download_queue.append((tframes, dest))

                else:
                    matched = fetch_frames_by_type(client, frames, mode, ft, args.tstart, args.tstop)
                    download_plan.append({"obsmode": mode, "frame_type": ft, "target_name": "-", "count": len(matched)})
                    if matched:
                        dest = resolve_dest(mode, ft)
                        download_queue.append((matched, dest))

    # --- Phase 2: download everything with a global counter ---
    total_files = sum(len(batch) for batch, _ in download_queue)
    downloaded_so_far = 0

    if not args.query_only:
        for batch, dest in download_queue:
            os.makedirs(dest, exist_ok=True)
            download_frames(batch, dest, offset=downloaded_so_far, total=total_files)
            downloaded_so_far += len(batch)

    print_download_table(download_plan, query_only=args.query_only)

    if not args.query_only and download_queue:
        full_path = os.path.abspath(base)
        logger.info(f"All files downloaded to: {full_path}")


def main():
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Download SOAR/Goodman frames from the LCO archive.",
        epilog=(
            "Examples:\n"
            "  %(prog)s --tstart 2024-06-01T00:00:00 --tstop 2024-06-02T00:00:00 --frame_type cals\n"
            "  %(prog)s --tstart 2024-06-01T00:00:00 --tstop 2024-06-02T00:00:00 --frame_type science --target_name SN2024abc\n"
            "  %(prog)s --tstart 2024-06-01T00:00:00 --tstop 2024-06-02T00:00:00 --frame_type science,cals --obs_mode photometry\n"
            "  %(prog)s --tstart 2024-06-01T00:00:00 --tstop 2024-06-02T00:00:00 --frame_type all --query_only\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--tstart", required=True,
                        help="Start time (ISO format, e.g. 2024-01-01T00:00:00)")
    parser.add_argument("--tstop", required=True,
                        help="Stop time (ISO format, e.g. 2024-01-02T00:00:00)")
    parser.add_argument("--obs_mode", choices=["photometry", "spectroscopy"],
                        help="Restrict to one observing mode (default: both)")
    parser.add_argument("--frame_type", nargs="+",
                        help="Frame types to download: bias, flats, arcs, science, standard, cals, all "
                             "(comma-separated or space-separated, e.g. --frame_type bias,flats)")
    parser.add_argument("--target_name", type=str,
                        help="Filter science frames to a specific target")
    parser.add_argument("--query_only", action="store_true",
                        help="Print the download table without downloading anything")
    parser.add_argument("--download_type", choices=["structured", "unstructured", "soar_dps"],
                        default="soar_dps",
                        help="Directory layout: structured (mode/frame_type/target), "
                             "unstructured (flat), soar_dps (mode/photometry/target/raw and mode/spectroscopy/raw) [default: soar_dps]")
    parser.add_argument("--dest_path", default="~/Downloads",
                        help="Base destination path for downloads (default: ~/Downloads). "
                             "The download folder soar_data_download_<DDMMYYHHMMSS> is created inside this path "
                             "for all download types (soar_dps, structured, unstructured).")
    parser.add_argument("--verify_bands", dest="verify_bands", action="store_true", default=True,
                        help="In soar_dps photometry mode, verify that every band with raw science data "
                             "also has LCO-reduced data; if a band is missing reduced data, download the "
                             "raw science frames (and bias/flats cals) for that band instead. (default: on)")
    parser.add_argument("--no_verify_bands", dest="verify_bands", action="store_false",
                        help="Disable band verification/fallback for soar_dps photometry mode.")


    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
