from pathlib import Path
import json
import re
import warnings
import pandas as pd

SUBJECTS = [f"sub-{i:02d}" for i in range(1, 7)]
EXPECTED_TR = 1.49
MULTIECHO_DATASETS = {"emotion-videos"}


def _run_key(nii_path: Path) -> str:
    """Return a run identity string by stripping echo-* and part-* entities."""
    stem = nii_path.name
    # strip .nii or .nii.gz
    stem = re.sub(r"\.nii(\.gz)?$", "", stem)
    stem = re.sub(r"_echo-[^_]+", "", stem)
    stem = re.sub(r"_part-[^_]+", "", stem)
    return stem


def _parse_run_duration(json_path: Path, dataset: str) -> float | None:
    """
    Return run duration in hours from a BIDS bold sidecar JSON.
    Returns None if volume count is unavailable.
    Warns if RepetitionTime differs from EXPECTED_TR (unless dataset is in MULTIECHO_DATASETS).
    """
    with open(json_path) as f:
        meta = json.load(f)

    tr = meta.get("RepetitionTime")
    if tr is None:
        warnings.warn(
            f"[{dataset}] {json_path.name}: 'RepetitionTime' field is missing from sidecar.",
            stacklevel=2,
        )
        return None

    if tr != EXPECTED_TR and dataset not in MULTIECHO_DATASETS:
        warnings.warn(
            f"[{dataset}] {json_path.name}: unexpected RepetitionTime={tr}s "
            f"(expected {EXPECTED_TR}s). This should not happen outside emotion-videos.",
            stacklevel=2,
        )

    acq_numbers = meta.get("time", {}).get("samples", {}).get("AcquisitionNumber", [])
    if acq_numbers:
        n_volumes = len(acq_numbers)
    else:
        # fallback: last dimension of dcmmeta_shape (nitransforms 4D shape)
        shape = meta.get("dcmmeta_shape")
        if shape and len(shape) == 4:
            n_volumes = shape[-1]
        else:
            warnings.warn(
                f"[{dataset}] {json_path.name}: cannot determine number of volumes "
                "(no time.samples.AcquisitionNumber and no dcmmeta_shape in sidecar). "
                "Run duration will be set to NaN.",
                stacklevel=2,
            )
            return None

    return n_volumes * tr / 3600.0


def compute_fmri_stats(source_dir: Path, out_file: Path) -> None:
    """
    Compute per-dataset fMRI run statistics and write a TSV + BIDS JSON sidecar.

    For each dataset, finds bold.nii* files under bids/sub-*/ses-*/,
    deduplicates multi-echo runs, reads companion JSON sidecars for volume counts,
    and computes: total_runs, avg_runs_per_session, avg_run_duration_h,
    avg_session_duration_h, total_duration_h.
    """
    records = []
    cneuromod_dir = source_dir / "cneuromod.all"

    for bids_dir in sorted(cneuromod_dir.glob("*/bids")):
        dataset = bids_dir.parent.name

        # collect all bold nii files across subjects/sessions
        all_nii = list(bids_dir.glob("sub-*/ses-*/func/*_bold.nii*"))
        if not all_nii:
            continue

        # deduplicate multi-echo/part runs: map run_key -> one representative nii path
        run_map: dict[str, Path] = {}
        for nii in sorted(all_nii):
            key = _run_key(nii)
            if key not in run_map:
                run_map[key] = nii

        # for each unique run, find its JSON sidecar and get duration
        run_durations: dict[str, float | None] = {}
        for key, nii in run_map.items():
            json_path = nii.with_suffix("").with_suffix(".json")
            if nii.suffix == ".gz":
                json_path = nii.with_name(nii.name[:-7] + ".json")
            else:
                json_path = nii.with_suffix(".json")

            if not json_path.exists():
                warnings.warn(
                    f"[{dataset}] Missing BIDS sidecar JSON for {nii.name} "
                    f"(expected {json_path.name}). Every bold.nii* must have a companion JSON.",
                    stacklevel=2,
                )
                run_durations[key] = None
            else:
                run_durations[key] = _parse_run_duration(json_path, dataset)

        # group runs by (subject, session) to compute per-session stats
        # run_key has the form sub-XX_ses-YY_..._bold
        session_runs: dict[tuple[str, str], list[float | None]] = {}
        for key in run_durations:
            m = re.match(r"(sub-\S+?)_(ses-\S+?)_", key)
            if m:
                sub, ses = m.group(1), m.group(2)
            else:
                sub, ses = "unknown", "unknown"
            session_runs.setdefault((sub, ses), []).append(run_durations[key])

        total_runs = len(run_durations)

        # per-session: count runs and sum duration (NaN if no volume counts available)
        runs_per_session = [len(v) for v in session_runs.values()]
        session_durations = []
        for v in session_runs.values():
            known = [d for d in v if d is not None]
            session_durations.append(sum(known) if known else float("nan"))

        avg_runs_per_session = sum(runs_per_session) / len(runs_per_session) if runs_per_session else 0.0

        durations_with_data = [d for d in run_durations.values() if d is not None]
        avg_run_duration_h = (
            sum(durations_with_data) / len(durations_with_data)
            if durations_with_data else float("nan")
        )

        known_sessions = [d for d in session_durations if not (d != d)]  # filter NaN
        avg_session_duration_h = (
            sum(known_sessions) / len(known_sessions)
            if known_sessions else float("nan")
        )
        total_duration_h = sum(known_sessions) if known_sessions else float("nan")

        records.append({
            "dataset": dataset,
            "total_runs": total_runs,
            "avg_runs_per_session": round(avg_runs_per_session, 2),
            "avg_run_duration_h": round(avg_run_duration_h, 4),
            "avg_session_duration_h": round(avg_session_duration_h, 4),
            "total_duration_h": round(total_duration_h, 4),
        })

    df = pd.DataFrame(records)
    df.to_csv(out_file, sep="\t", index=False)
    print(f"fMRI stats saved to {out_file}")

    _write_bids_sidecar(out_file)


def _write_bids_sidecar(tsv_path: Path) -> None:
    """Write a BIDS-style JSON sidecar describing the columns of the fMRI stats TSV."""
    sidecar = {
        "dataset": {
            "Description": "Name of the CNeuroMod dataset."
        },
        "total_runs": {
            "Description": (
                "Total number of unique fMRI runs across all subjects and sessions. "
                "Multi-echo acquisitions (e.g. emotion-videos) are counted as one run "
                "regardless of the number of echoes or parts."
            )
        },
        "avg_runs_per_session": {
            "Description": (
                "Average number of fMRI runs per scanning session, computed as the mean "
                "across all (subject, session) pairs with at least one run."
            )
        },
        "avg_run_duration_h": {
            "Description": (
                "Average duration of a single fMRI run in hours, computed from the number "
                "of brain volumes (length of time.samples.AcquisitionNumber in the BIDS "
                "sidecar JSON) multiplied by the RepetitionTime."
            ),
            "Units": "hours"
        },
        "avg_session_duration_h": {
            "Description": (
                "Average total fMRI acquisition time per scanning session in hours, "
                "computed as the sum of all run durations within a session, then averaged "
                "across all (subject, session) pairs."
            ),
            "Units": "hours"
        },
        "total_duration_h": {
            "Description": (
                "Total cumulative fMRI acquisition time for the dataset across all subjects "
                "and sessions, in hours."
            ),
            "Units": "hours"
        },
    }
    json_path = tsv_path.with_suffix(".json")
    with open(json_path, "w") as f:
        json.dump(sidecar, f, indent=2)
    print(f"BIDS sidecar saved to {json_path}")


def count_sessions(source_dir: Path, out_file: Path) -> None:
    """Count BIDS sessions per subject per dataset and write a TSV."""
    records = []
    cneuromod_dir = source_dir / "cneuromod.all"

    for bids_dir in sorted(cneuromod_dir.glob("*/bids")):
        dataset = bids_dir.parent.name
        for subject in SUBJECTS:
            sub_dir = bids_dir / subject
            if not sub_dir.exists():
                n_sessions = 0
            else:
                sessions = list(sub_dir.glob("ses-*"))
                if sessions:
                    n_sessions = len(sessions)
                else:
                    # No session level: count as 1 if the subject folder has content
                    n_sessions = 1 if any(sub_dir.iterdir()) else 0
            records.append({"dataset": dataset, "subject": subject, "n_sessions": n_sessions})

    df = pd.DataFrame(records)
    df.to_csv(out_file, sep="\t", index=False)
    print(f"Session counts saved to {out_file}")
