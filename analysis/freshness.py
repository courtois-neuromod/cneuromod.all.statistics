"""Fingerprint each dataset's remote inputs so `refresh` rebuilds only what changed.

A dataset is *stale* when any of its source subdatasets (bids, physprep,
fmriprep, tsnr, timeseries) has a different remote HEAD or git-annex branch than
the one recorded at the last refresh, or when the pipeline code itself changed.
"""
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
KINDS = ("bids", "physprep", "fmriprep", "tsnr", "timeseries")
CODE_PATHS = ("tasks.py", "analysis", "dashboard", "invoke.yaml", "uv.lock")
STATE_FILE = "SOURCE_STATE.json"


def _git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


def submodule_urls(cneuromod_all_dir):
    """{submodule path: url} read from the superdataset's .gitmodules."""
    out = _git("config", "-f", ".gitmodules", "--get-regexp", r"submodule\..*\.(path|url)",
               cwd=cneuromod_all_dir)
    paths, urls = {}, {}
    for line in out.splitlines():
        key, value = line.split(maxsplit=1)
        name, field = key[len("submodule."):].rsplit(".", 1)
        (paths if field == "path" else urls)[name] = value
    return {paths[n]: urls[n] for n in paths if n in urls}


def parse_ls_remote(text):
    """(head, annex) shas from `git ls-remote <url> HEAD refs/heads/git-annex` output."""
    refs = {}
    for line in text.splitlines():
        sha, ref = line.split()
        refs[ref] = sha
    return {"head": refs.get("HEAD"), "annex": refs.get("refs/heads/git-annex")}


def _ls_remote(url):
    return parse_ls_remote(_git("ls-remote", url, "HEAD", "refs/heads/git-annex"))


def source_heads(cneuromod_all_dir, kinds=KINDS, max_workers=8):
    """{dataset: {kind: {head, annex}}} for every `<dataset>/<kind>` submodule.

    Raises if any remote cannot be read: a partial state must never be recorded.
    """
    wanted = {}
    for path, url in submodule_urls(cneuromod_all_dir).items():
        parts = path.split("/")
        if len(parts) == 2 and parts[1] in kinds:
            wanted[tuple(parts)] = url
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(_ls_remote, wanted.values()))
    heads = {}
    for (dataset, kind), res in zip(wanted, results):
        heads.setdefault(dataset, {})[kind] = res
    return heads


def code_hash(repo):
    """Combined git tree ids of the paths that determine the outputs."""
    return ",".join(_git("rev-parse", f"HEAD:{p}", cwd=repo).strip() for p in CODE_PATHS)


def stale_datasets(current, recorded, code, recorded_code=None):
    """{dataset: [reasons]} for datasets whose inputs differ from `recorded`.

    `recorded` is the `datasets` mapping of the saved state (or {}); a code change
    makes every dataset stale.
    """
    code_changed = recorded_code != code
    stale = {}
    for dataset, kinds in sorted(current.items()):
        reasons = []
        if code_changed and recorded_code:
            reasons.append("pipeline code changed")
        old = recorded.get(dataset, {})
        if not old:
            reasons.append("no recorded state")
        for kind in sorted(set(kinds) | set(old)) if old else ():
            for field in ("head", "annex"):
                new_v = kinds.get(kind, {}).get(field)
                old_v = old.get(kind, {}).get(field)
                if new_v != old_v:
                    reasons.append(f"{kind} {field}: {(old_v or 'none')[:8]} -> {(new_v or 'none')[:8]}")
        if reasons:
            stale[dataset] = reasons
    return stale


def read_state(output_dir):
    path = Path(output_dir) / STATE_FILE
    if not path.exists():
        return {"code_hash": None, "datasets": {}}
    state = json.loads(path.read_text())
    if state.get("schema") != SCHEMA:
        return {"code_hash": None, "datasets": {}}
    return state


def write_state(output_dir, code, datasets):
    state = {"schema": SCHEMA, "code_hash": code,
             "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "datasets": datasets}
    (Path(output_dir) / STATE_FILE).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def regressions(before, after, datasets):
    """Human-readable drops in `n_judged` / `n_on_*` between two completeness summaries.

    `before` and `after` are DataFrames (completeness_summary.tsv); only rows of
    `datasets` are compared, summed over subjects per (dataset, asset). A missing
    (dataset, asset) in `after` counts as a drop to zero.
    """
    cols = [c for c in before.columns if c == "n_judged" or c.startswith("n_on_")]
    key = ["dataset", "asset"]
    old = before[before["dataset"].isin(datasets)].groupby(key)[cols].sum(min_count=1).fillna(0)
    new = after[after["dataset"].isin(datasets)].groupby(key)[cols].sum(min_count=1).fillna(0)
    new = new.reindex(old.index, fill_value=0)
    out = []
    for idx in old.index:
        for col in cols:
            if new.loc[idx, col] < old.loc[idx, col]:
                out.append(f"{idx[0]}/{idx[1]} {col}: {int(old.loc[idx, col])} -> {int(new.loc[idx, col])}")
    return out
