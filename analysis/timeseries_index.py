"""Which runs each timeseries h5 holds.

CNeuroMod timeseries are one `.h5` per subject x atlas, with one dataset per run
(`ses-XXX/ses-XXX_task-..._timeseries`, or flat for session-less datasets). Run
names live in the HDF5 metadata, so they can be listed from the local file when
its content is present, or with ranged reads from the S3 remote (which is
private: credentials come from the AWS_* variables git-annex itself uses) —
without downloading the signals.
"""
from pathlib import Path
import os

import pandas as pd

from analysis.annex import named_remotes, _git

COLUMNS = ["dataset", "subject", "atlas", "key", "session", "run_key", "n_timepoints"]


def h5_files(ts_repo: Path, atlas: str) -> dict[str, Path]:
    """Return {subject: h5 path} for an atlas of a timeseries subdataset (links may be dangling)."""
    out = {}
    for sub_dir in sorted((ts_repo / "timeseries" / atlas).glob("sub-*")):
        files = sorted(sub_dir.glob("*_timeseries.h5"))
        if files:
            out[sub_dir.name] = files[0]
    return out


def annex_key(path: Path) -> str | None:
    """The annex key of a (possibly dangling) annexed symlink, else None."""
    if path.is_symlink():
        return Path(os.readlink(path)).name
    return None


def s3_settings(ts_repo: Path) -> dict | None:
    """Bucket and endpoint of the S3 remote of a timeseries repo, from `remote.log`."""
    names = named_remotes(ts_repo)
    for line in _git(ts_repo, "show", "git-annex:remote.log").splitlines():
        uuid, _, rest = line.partition(" ")
        fields = dict(f.partition("=")[::2] for f in rest.split(" ") if "=" in f)
        if fields.get("type") == "S3" and fields.get("name", "").endswith("timeseries"):
            return {
                "bucket": fields["bucket"],
                "endpoint": f"{fields.get('protocol', 'https')}://{fields['host']}:{fields.get('port', 443)}",
                "chunk": fields.get("chunk"),
            }
    return None


def _open_remote(key: str, s3: dict):
    """Open the object of an annex key in the S3 remote as a seekable file (ranged reads only)."""
    import s3fs

    fs = s3fs.S3FileSystem(
        key=os.environ["AWS_ACCESS_KEY_ID"],
        secret=os.environ["AWS_SECRET_ACCESS_KEY"],
        client_kwargs={"endpoint_url": s3["endpoint"]},
        config_kwargs={"s3": {"addressing_style": "path"}},
        default_block_size=1 << 20,
    )
    # unchunked objects are stored under the plain key; chunked ones under chunk keys
    for candidate in (key, key.replace("--", "-S1073741824-C1--", 1)):
        path = f"{s3['bucket']}/{candidate}"
        if fs.exists(path):
            return fs.open(path, "rb")
    raise FileNotFoundError(f"{key} not in s3://{s3['bucket']}")


def list_runs(f, subject: str) -> list[dict]:
    """Run groups of an open h5: session, run_key and number of timepoints."""
    import h5py

    rows = []

    def add(session: str, name: str, ds) -> None:
        stem = name[: -len("_timeseries")] if name.endswith("_timeseries") else name
        rows.append({
            "session": session,
            "run_key": f"{subject}_{stem}",
            "n_timepoints": int(ds.shape[0]) if ds.shape else None,
        })

    for top, node in f.items():
        if isinstance(node, h5py.Dataset):
            add("", top, node)
        else:
            for name, ds in node.items():
                add(top, name, ds)
    return rows


def index_h5(path: Path, ts_repo: Path, subject: str) -> list[dict] | None:
    """List the runs of one h5 from local content or S3; None when neither is reachable."""
    import h5py

    if path.exists():
        with h5py.File(path, "r") as f:
            return list_runs(f, subject)
    key = annex_key(path)
    s3 = s3_settings(ts_repo)
    if key and s3 and "AWS_ACCESS_KEY_ID" in os.environ:
        with _open_remote(key, s3) as fobj, h5py.File(fobj, "r") as f:
            return list_runs(f, subject)
    return None


def build_index(
    cneuromod_all_dir: Path, atlases: list[str], datasets: set[str] | None,
    previous: pd.DataFrame,
) -> pd.DataFrame:
    """Refresh the index: files whose annex key is unchanged keep their previous rows."""
    kept = previous.copy()
    new_rows = []
    for ts_repo in sorted(cneuromod_all_dir.glob("*/timeseries")):
        dataset = ts_repo.parent.name
        if datasets is not None and dataset not in datasets:
            continue
        for atlas in atlases:
            for subject, path in h5_files(ts_repo, atlas).items():
                key = annex_key(path) or ""
                same = (kept["dataset"] == dataset) & (kept["subject"] == subject) & (kept["atlas"] == atlas)
                if key and (kept.loc[same, "key"] == key).any():
                    print(f"  {dataset}/{atlas}/{subject}: unchanged")
                    continue
                try:
                    runs = index_h5(path, ts_repo, subject)
                except Exception as exc:  # unreachable or unreadable: keep going
                    print(f"  {dataset}/{atlas}/{subject}: failed ({type(exc).__name__}: {exc})")
                    continue
                if runs is None:
                    print(f"  {dataset}/{atlas}/{subject}: content unreachable (no local copy, no S3 credentials)")
                    continue
                kept = kept[~same]
                new_rows += [{"dataset": dataset, "subject": subject, "atlas": atlas, "key": key, **r} for r in runs]
                print(f"  {dataset}/{atlas}/{subject}: {len(runs)} runs")
    out = pd.concat([kept, pd.DataFrame(new_rows, columns=COLUMNS)], ignore_index=True)
    return out.sort_values(["dataset", "atlas", "subject", "session", "run_key"]).reset_index(drop=True)
