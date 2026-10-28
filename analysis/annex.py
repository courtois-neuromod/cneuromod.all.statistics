"""Where each annexed file of a cneuromod.all subdataset can be retrieved from.

Annex location logs live in the `git-annex` branch, so they are readable offline.
But a repo lists hundreds of locations (mostly temporary job clones), so only a
curated set of *release remotes* is kept, each under one label, with `sameas`
aliases (e.g. `conp-ria-storage-http` -> `conp-ria-storage`) folded in.

`git annex whereis` merges `origin/git-annex` into the local branch (a write in
the source checkout), so this module is for `fetch` only, never for `run`.
"""
from fnmatch import fnmatch
from pathlib import Path
import json
import subprocess

import pandas as pd

# What each subdataset kind contributes to run-level completeness
INCLUDE_GLOBS = {
    "bids": ["*_bold.nii.gz", "*_bold.nii", "*_physio.tsv.gz"],
    "fmriprep": ["*desc-preproc*_bold.nii.gz"],
    "tsnr": ["*stat-tsnr_statmap.nii.gz"],
    "physprep": ["*desc-preproc_physio.tsv.gz"],
    "timeseries": ["*_timeseries.h5"],
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def named_remotes(repo: Path) -> dict[str, set[str]]:
    """Return {uuid: {names}} from the repo's `remote.log` (a name or a `sameas-name`)."""
    names: dict[str, set[str]] = {}
    for line in _git(repo, "show", "git-annex:remote.log").splitlines():
        if not line.strip():
            continue
        uuid, _, rest = line.partition(" ")
        fields = dict(f.partition("=")[::2] for f in rest.split(" ") if "=" in f)
        name = fields.get("name") or fields.get("sameas-name")
        if name:
            names.setdefault(uuid, set()).add(name)
        # a `sameas` remote shares the content of the remote it points at
        if "sameas-uuid" in fields and "sameas-name" in fields:
            names.setdefault(fields["sameas-uuid"], set()).add(fields["sameas-name"])
    return names


def uuid_labels(repo: Path, release_remotes: dict[str, list[str]]) -> dict[str, str]:
    """Map annex uuids to release-remote labels (first label whose pattern matches a name)."""
    labels = {}
    for uuid, names in named_remotes(repo).items():
        for label, patterns in release_remotes.items():
            if any(fnmatch(n, p) for n in names for p in patterns):
                labels[uuid] = label
                break
    return labels


def annex_locations(
    repo: Path, kind: str, release_remotes: dict[str, list[str]]
) -> tuple[pd.DataFrame, set[str]]:
    """One row per annexed file of `kind`: path, key and the `;`-joined release labels holding it.

    Also returns the names of the remotes holding files that match no release
    label, so a missing pattern in `release_remotes` is easy to spot.
    """
    cmd = ["git", "-C", str(repo), "annex", "whereis", "--json", "--fast"]
    # git-annex ANDs adjacent matching options; --or makes the globs alternatives
    for i, pattern in enumerate(INCLUDE_GLOBS[kind]):
        cmd += (["--or"] if i else []) + [f"--include={pattern}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 1):  # 1: some file could not be examined
        raise RuntimeError(f"git annex whereis failed in {repo}: {proc.stderr.strip()[:300]}")

    labels = uuid_labels(repo, release_remotes)
    all_names = named_remotes(repo)
    rows, unmatched = [], set()
    for line in proc.stdout.splitlines():
        rec = json.loads(line)
        if not rec.get("success", True) or "whereis" not in rec:
            continue
        held = set()
        for loc in rec["whereis"]:
            if loc["uuid"] in labels:
                held.add(labels[loc["uuid"]])
            else:
                unmatched |= all_names.get(loc["uuid"], set())
        rows.append({
            "path": rec["file"],
            "key": rec["key"],
            "remotes": ";".join(sorted(held)),
        })
    return pd.DataFrame(rows, columns=["path", "key", "remotes"]), unmatched
