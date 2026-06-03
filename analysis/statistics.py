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


def _parse_run_info(json_path: Path, dataset: str) -> tuple[int | None, float | None]:
    """
    Return (n_volumes, duration_h) from a BIDS bold sidecar JSON.
    Both are None if volume count is unavailable.
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
        return None, None

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
            return None, None

    return n_volumes, n_volumes * tr / 3600.0


def _filter_nan(values: list) -> list:
    """Return values with NaN entries removed."""
    return [v for v in values if v == v]


def _collect_run_map(bids_dir: Path) -> dict[str, Path]:
    """Return {run_key: representative_nii_path} for all unique bold runs under bids_dir."""
    run_map: dict[str, Path] = {}
    for nii in sorted(bids_dir.glob("sub-*/ses-*/func/*_bold.nii*")):
        key = _run_key(nii)
        if key not in run_map:
            run_map[key] = nii
    # also handle session-less BIDS layout (e.g. harrypotter)
    for nii in sorted(bids_dir.glob("sub-*/func/*_bold.nii*")):
        key = _run_key(nii)
        if key not in run_map:
            run_map[key] = nii
    return run_map


def _load_run_data(
    run_map: dict[str, Path], dataset: str
) -> tuple[dict[str, int | None], dict[str, float | None]]:
    """
    Parse BIDS sidecar JSONs for all runs in run_map.
    Returns (run_volumes, run_durations) dicts keyed by run_key.
    """
    run_volumes: dict[str, int | None] = {}
    run_durations: dict[str, float | None] = {}
    for key, nii in run_map.items():
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
            run_volumes[key] = None
            run_durations[key] = None
        else:
            n_vol, dur = _parse_run_info(json_path, dataset)
            run_volumes[key] = n_vol
            run_durations[key] = dur
    return run_volumes, run_durations


def _group_by_session(
    run_volumes: dict[str, int | None],
    run_durations: dict[str, float | None],
) -> dict[tuple[str, str], list[tuple[int | None, float | None]]]:
    """Group (n_vol, dur) pairs by (subject, session) parsed from run keys."""
    session_runs: dict[tuple[str, str], list] = {}
    for key in run_durations:
        m = re.match(r"(sub-\S+?)_(ses-\S+?)_", key)
        if m:
            sub, ses = m.group(1), m.group(2)
        else:
            # session-less layout (e.g. harrypotter): no ses- entity in key
            m2 = re.match(r"(sub-\S+?)_", key)
            sub = m2.group(1) if m2 else "unknown"
            ses = "ses-01"
        session_runs.setdefault((sub, ses), []).append((run_volumes[key], run_durations[key]))
    return session_runs


def _session_aggregates(
    session_runs: dict[tuple[str, str], list],
) -> tuple[list[int], list[float], list[float]]:
    """
    Return (runs_per_session, session_durations, session_volumes) from session_runs.
    NaN is used for sessions where all runs have unknown duration/volumes.
    """
    runs_per_session = [len(v) for v in session_runs.values()]
    session_durations = []
    session_volumes = []
    for v in session_runs.values():
        known_dur = [d for _, d in v if d is not None]
        known_vol = [n for n, _ in v if n is not None]
        session_durations.append(sum(known_dur) if known_dur else float("nan"))
        session_volumes.append(sum(known_vol) if known_vol else float("nan"))
    return runs_per_session, session_durations, session_volumes


def _dataset_record(
    dataset: str,
    run_volumes: dict[str, int | None],
    run_durations: dict[str, float | None],
    session_runs: dict[tuple[str, str], list],
) -> dict:
    """Compute aggregate fMRI stats for one dataset and return as a record dict."""
    runs_per_session, session_durations, session_volumes = _session_aggregates(session_runs)
    total_runs = len(run_durations)

    avg_runs_per_session = sum(runs_per_session) / len(runs_per_session) if runs_per_session else 0.0

    durations_with_data = [d for d in run_durations.values() if d is not None]
    avg_run_duration_h = (
        sum(durations_with_data) / len(durations_with_data) if durations_with_data else float("nan")
    )

    known_ses_dur = _filter_nan(session_durations)
    avg_session_duration_h = (
        sum(known_ses_dur) / len(known_ses_dur) if known_ses_dur else float("nan")
    )
    total_duration_h = sum(known_ses_dur) if known_ses_dur else float("nan")

    volumes_with_data = [n for n in run_volumes.values() if n is not None]
    total_volumes = sum(volumes_with_data) if volumes_with_data else float("nan")
    avg_volumes_per_run = (
        sum(volumes_with_data) / len(volumes_with_data) if volumes_with_data else float("nan")
    )
    known_ses_vol = _filter_nan(session_volumes)
    avg_volumes_per_session = (
        sum(known_ses_vol) / len(known_ses_vol) if known_ses_vol else float("nan")
    )

    return {
        "dataset": dataset,
        "total_runs": total_runs,
        "avg_runs_per_session": round(avg_runs_per_session, 2),
        "avg_run_duration_h": round(avg_run_duration_h, 4),
        "avg_session_duration_h": round(avg_session_duration_h, 4),
        "total_duration_h": round(total_duration_h, 4),
        "total_volumes": int(total_volumes) if total_volumes == total_volumes else float("nan"),
        "avg_volumes_per_run": round(avg_volumes_per_run, 1) if avg_volumes_per_run == avg_volumes_per_run else float("nan"),
        "avg_volumes_per_session": round(avg_volumes_per_session, 1) if avg_volumes_per_session == avg_volumes_per_session else float("nan"),
    }


def _all_row(df: pd.DataFrame) -> dict:
    """Compute the cumulative 'all' row from a per-dataset stats DataFrame."""
    total_runs_all = int(df["total_runs"].sum())
    total_duration_all = df["total_duration_h"].sum(skipna=True)
    total_volumes_all = df["total_volumes"].sum(skipna=True)
    return {
        "dataset": "all",
        "total_runs": total_runs_all,
        "avg_runs_per_session": round(df["avg_runs_per_session"].mean(skipna=True), 2),
        "avg_run_duration_h": round(total_duration_all / total_runs_all, 4) if total_runs_all else float("nan"),
        "avg_session_duration_h": round(df["avg_session_duration_h"].mean(skipna=True), 4),
        "total_duration_h": round(total_duration_all, 4),
        "total_volumes": int(total_volumes_all) if not pd.isna(total_volumes_all) else float("nan"),
        "avg_volumes_per_run": round(total_volumes_all / total_runs_all, 1) if total_runs_all else float("nan"),
        "avg_volumes_per_session": round(df["avg_volumes_per_session"].mean(skipna=True), 1),
    }


def compute_fmri_stats(cneuromod_all_dir: Path, out_file: Path) -> None:
    """
    Compute per-dataset fMRI run statistics and write a TSV + BIDS JSON sidecar.

    For each dataset, finds bold.nii* files under bids/sub-*/ses-*/,
    deduplicates multi-echo runs, reads companion JSON sidecars for volume counts,
    and computes: total_runs, avg_runs_per_session, avg_run_duration_h,
    avg_session_duration_h, total_duration_h, total_volumes, avg_volumes_per_run,
    avg_volumes_per_session.
    """
    records = []
    for bids_dir in sorted(cneuromod_all_dir.glob("*/bids")):
        dataset = bids_dir.parent.name
        run_map = _collect_run_map(bids_dir)
        if not run_map:
            continue
        run_volumes, run_durations = _load_run_data(run_map, dataset)
        session_runs = _group_by_session(run_volumes, run_durations)
        records.append(_dataset_record(dataset, run_volumes, run_durations, session_runs))

    df = pd.DataFrame(records)
    df = pd.concat([df, pd.DataFrame([_all_row(df)])], ignore_index=True)
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
        "total_volumes": {
            "Description": (
                "Total number of brain volumes (TRs) acquired across all subjects, sessions, "
                "and runs in the dataset."
            ),
            "Units": "volumes"
        },
        "avg_volumes_per_run": {
            "Description": (
                "Average number of brain volumes per fMRI run, computed as the mean across "
                "all unique runs in the dataset."
            ),
            "Units": "volumes"
        },
        "avg_volumes_per_session": {
            "Description": (
                "Average total number of brain volumes per scanning session, computed as the "
                "mean across all (subject, session) pairs."
            ),
            "Units": "volumes"
        },
    }
    json_path = tsv_path.with_suffix(".json")
    with open(json_path, "w") as f:
        json.dump(sidecar, f, indent=2)
    print(f"BIDS sidecar saved to {json_path}")


def compute_fmri_stats_per_subject(cneuromod_all_dir: Path, out_file: Path) -> None:
    """
    Compute per-dataset, per-subject fMRI run statistics and write a TSV.

    For each (dataset, subject), computes: total_runs, avg_runs_per_session,
    avg_session_duration_h, total_duration_h, total_volumes, avg_volumes_per_session.
    """
    records = []

    for bids_dir in sorted(cneuromod_all_dir.glob("*/bids")):
        dataset = bids_dir.parent.name
        run_map = _collect_run_map(bids_dir)
        if not run_map:
            continue
        run_volumes, run_durations = _load_run_data(run_map, dataset)
        session_runs = _group_by_session(run_volumes, run_durations)

        # aggregate per subject
        subject_sessions: dict[str, list[tuple[str, str]]] = {}
        for (sub, ses) in session_runs:
            subject_sessions.setdefault(sub, []).append((sub, ses))

        for subject in SUBJECTS:
            sub_sessions = subject_sessions.get(subject, [])
            if not sub_sessions:
                records.append({
                    "dataset": dataset, "subject": subject,
                    "total_runs": 0,
                    "avg_runs_per_session": float("nan"),
                    "avg_session_duration_h": float("nan"),
                    "total_duration_h": float("nan"),
                    "total_volumes": float("nan"),
                    "avg_volumes_per_session": float("nan"),
                })
                continue

            runs_per_ses = [len(session_runs[key]) for key in sub_sessions]
            session_durations = []
            session_volumes = []
            for key in sub_sessions:
                known_dur = [d for _, d in session_runs[key] if d is not None]
                known_vol = [n for n, _ in session_runs[key] if n is not None]
                session_durations.append(sum(known_dur) if known_dur else float("nan"))
                session_volumes.append(sum(known_vol) if known_vol else float("nan"))

            total_runs = sum(runs_per_ses)
            avg_runs_per_session = total_runs / len(runs_per_ses)
            known_ses_dur = _filter_nan(session_durations)
            avg_session_duration_h = sum(known_ses_dur) / len(known_ses_dur) if known_ses_dur else float("nan")
            total_duration_h = sum(known_ses_dur) if known_ses_dur else float("nan")

            known_ses_vol = _filter_nan(session_volumes)
            total_volumes = int(sum(known_ses_vol)) if known_ses_vol else float("nan")
            avg_volumes_per_session = sum(known_ses_vol) / len(known_ses_vol) if known_ses_vol else float("nan")

            records.append({
                "dataset": dataset,
                "subject": subject,
                "total_runs": total_runs,
                "avg_runs_per_session": round(avg_runs_per_session, 2),
                "avg_session_duration_h": round(avg_session_duration_h, 4),
                "total_duration_h": round(total_duration_h, 4),
                "total_volumes": total_volumes,
                "avg_volumes_per_session": round(avg_volumes_per_session, 1) if avg_volumes_per_session == avg_volumes_per_session else float("nan"),
            })

    df = pd.DataFrame(records)

    # Append cumulative "all" rows — one per subject, summing across datasets
    all_records = []
    for subject in SUBJECTS:
        sub_df = df[df["subject"] == subject]
        has_data = sub_df[sub_df["total_runs"] > 0]
        total_runs = int(sub_df["total_runs"].sum())
        total_duration = has_data["total_duration_h"].sum(skipna=True)
        total_volumes = has_data["total_volumes"].sum(skipna=True)
        all_records.append({
            "dataset": "all",
            "subject": subject,
            "total_runs": total_runs,
            "avg_runs_per_session": round(has_data["avg_runs_per_session"].mean(skipna=True), 2) if len(has_data) else float("nan"),
            "avg_session_duration_h": round(has_data["avg_session_duration_h"].mean(skipna=True), 4) if len(has_data) else float("nan"),
            "total_duration_h": round(total_duration, 4),
            "total_volumes": int(total_volumes) if not pd.isna(total_volumes) else float("nan"),
            "avg_volumes_per_session": round(has_data["avg_volumes_per_session"].mean(skipna=True), 1) if len(has_data) else float("nan"),
        })
    df = pd.concat([df, pd.DataFrame(all_records)], ignore_index=True)

    df.to_csv(out_file, sep="\t", index=False)
    print(f"fMRI per-subject stats saved to {out_file}")


def count_sessions(cneuromod_all_dir: Path, out_file: Path) -> None:
    """Count BIDS sessions per subject per dataset and write a TSV."""
    records = []

    for bids_dir in sorted(cneuromod_all_dir.glob("*/bids")):
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
