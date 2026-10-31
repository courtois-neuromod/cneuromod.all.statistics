from pathlib import Path
from invoke import task


def _cneuromod_dir(c) -> Path:
    """Where the cneuromod.all superdataset is made available under source_data/."""
    return Path(c.config.get("datasets", {}).get("cneuromod_all", {})["output_dir"])


@task(help={
    "source": "Path to an existing local cneuromod.all checkout to symlink "
              "instead of cloning (defaults to the `source:` key in "
              "invoke.yaml, i.e. ../cneuromod.all).",
})
def fetch_cneuromod(c, source=None):
    """Make the cneuromod.all superdataset available under source_data/ (symlink or clone, tree only)."""
    from airoh.datalad import install_dataset
    install_dataset(c, "cneuromod_all", source=source)


def _install_subdatasets(c, kind, dataset, strict):
    """Install every dataset's `<kind>/` subdataset (tree only), optionally for a subset of datasets."""
    from airoh.datalad import install_subdataset

    root = _cneuromod_dir(c)
    if not root.is_dir():
        print(f"⚠️  {root} not found — run `invoke fetch-cneuromod` first.")
        return

    names = {n.strip() for n in dataset.split(",")} if dataset else None
    for sub_dir in sorted(root.glob(f"*/{kind}")):
        name = sub_dir.parent.name
        if names is not None and name not in names:
            continue
        print(f"Installing {name}/{kind}...")
        install_subdataset(f"{name}/{kind}", root, strict=strict)


@task(help={
    "dataset": "Comma-separated cneuromod.all dataset names to restrict the fetch to "
              "(default: every dataset with a `bids/` subfolder).",
    "strict": "Raise if a bids subdataset fails to install.",
})
def fetch_bids(c, dataset=None, strict=False):
    """Install each dataset's `bids/` subdataset (tree only, no annexed content)."""
    _install_subdatasets(c, "bids", dataset, strict)


@task(help={
    "dataset": "Comma-separated cneuromod.all dataset names to restrict the fetch to "
              "(default: every dataset with a `physprep/` subfolder).",
    "strict": "Raise if a physprep subdataset fails to install.",
})
def fetch_physprep(c, dataset=None, strict=False):
    """Install each dataset's `physprep/` subdataset (tree only, for the plain-git QC JSONs)."""
    _install_subdatasets(c, "physprep", dataset, strict)


@task(help={
    "dataset": "Comma-separated cneuromod.all dataset names to restrict the fetch to "
              "(default: every dataset with a `fmriprep/` subfolder).",
    "strict": "Raise if a fmriprep subdataset fails to install.",
})
def fetch_fmriprep(c, dataset=None, strict=False):
    """Install each dataset's `fmriprep/` subdataset (tree only, for run-level completeness)."""
    _install_subdatasets(c, "fmriprep", dataset, strict)


@task(help={
    "dataset": "Comma-separated cneuromod.all dataset names to restrict the fetch to "
              "(default: every dataset with a `tsnr/` subfolder).",
    "strict": "Raise if a tsnr subdataset fails to install.",
})
def fetch_tsnr(c, dataset=None, strict=False):
    """Install each dataset's `tsnr/` subdataset (tree only, for run-level completeness)."""
    _install_subdatasets(c, "tsnr", dataset, strict)


@task(help={
    "dataset": "Comma-separated cneuromod.all dataset names to restrict the fetch to "
              "(default: every dataset with a `timeseries/` subfolder).",
    "strict": "Raise if a timeseries subdataset fails to install.",
})
def fetch_timeseries(c, dataset=None, strict=False):
    """Install each dataset's `timeseries/` subdataset (tree only, for run-level completeness)."""
    _install_subdatasets(c, "timeseries", dataset, strict)


@task(help={
    "dataset": "Comma-separated dataset names to restrict the index to.",
})
def fetch_annex_locations(c, dataset=None):
    """Index which release remotes hold each bold/physio/fmriprep/tsnr/physprep/timeseries file.

    Runs `git annex whereis`, which merges origin/git-annex in the source
    checkout — so it belongs here and never in `run`.
    """
    from analysis.annex import INCLUDE_GLOBS, annex_locations

    root = _cneuromod_dir(c)
    out_dir = Path(c.config.get("source_data_dir")) / "annex_locations"
    out_dir.mkdir(parents=True, exist_ok=True)
    release_remotes = dict(c.config.get("release_remotes", {}))
    names = {n.strip() for n in dataset.split(",")} if dataset else None

    unmatched = {}
    for kind in INCLUDE_GLOBS:
        for repo in sorted(root.glob(f"*/{kind}")):
            name = repo.parent.name
            if names is not None and name not in names:
                continue
            if not (repo / ".git").exists():
                print(f"  {name}/{kind}: not installed, skipped")
                continue
            df, left_out = annex_locations(repo, kind, release_remotes)
            df.to_csv(out_dir / f"{name}_{kind}.tsv", sep="\t", index=False)
            unmatched.setdefault(name, set()).update(left_out)
            print(f"  {name}/{kind}: {len(df)} files")
    for name, left_out in sorted(unmatched.items()):
        if left_out:
            print(f"  [{name}] remotes not counted as release remotes: {', '.join(sorted(left_out))}")


@task(help={
    "dataset": "Comma-separated dataset names to restrict the index to.",
    "atlas": "Comma-separated atlases (default: `timeseries_atlases` in invoke.yaml).",
})
def fetch_timeseries_index(c, dataset=None, atlas=None):
    """List the runs held by each timeseries h5 (local content, else ranged reads from S3).

    S3 access needs AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in the environment.
    Files whose annex key is unchanged since the last index are skipped.
    """
    import pandas as pd
    from analysis.timeseries_index import COLUMNS, build_index

    out_file = Path(c.config.get("source_data_dir")) / "timeseries_index.tsv"
    atlases = [a.strip() for a in atlas.split(",")] if atlas else list(c.config.get("timeseries_atlases", []))
    names = {n.strip() for n in dataset.split(",")} if dataset else None
    previous = (pd.read_csv(out_file, sep="\t", keep_default_na=False, dtype={"session": str})
                if out_file.exists() else pd.DataFrame(columns=COLUMNS))
    index = build_index(_cneuromod_dir(c), atlases, names, previous)
    index.to_csv(out_file, sep="\t", index=False)
    print(f"Saved {len(index)} timeseries runs to {out_file.name}")


@task(help={
    "source": "Path to an existing local cneuromod.all checkout to symlink instead of cloning.",
    "dataset": "Comma-separated dataset names to restrict the bids fetch to.",
    "strict": "Raise if a bids or physprep subdataset fails to install.",
})
def fetch(c, source=None, dataset=None, strict=False):
    """Retrieve all source data: cneuromod.all, every dataset's bids, physprep, fmriprep, tsnr and timeseries trees, and the annex-location and timeseries indexes."""
    from airoh.provenance import record_sources

    fetch_cneuromod(c, source=source)
    fetch_bids(c, dataset=dataset, strict=strict)
    fetch_physprep(c, dataset=dataset, strict=strict)
    fetch_fmriprep(c, dataset=dataset, strict=strict)
    fetch_tsnr(c, dataset=dataset, strict=strict)
    fetch_timeseries(c, dataset=dataset, strict=strict)
    fetch_annex_locations(c, dataset=dataset)
    fetch_timeseries_index(c, dataset=dataset)
    record_sources(c)
    print("✅ fetch complete.")


@task
def run_statistics(c):
    """Count sessions per subject per dataset; save to output_data/session_counts.tsv."""
    from airoh.utils import ensure_dir_exist
    from analysis.statistics import count_sessions

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "session_counts.tsv"

    if out_file.exists():
        print(f"Skipping run-statistics (output exists: {out_file})")
        return

    ensure_dir_exist(c, "output_data_dir")
    count_sessions(cneuromod_all_dir, out_file)


@task
def run_fmri_stats(c):
    """Compute fMRI run stats per dataset; save to output_data/fmri_stats.tsv."""
    from airoh.utils import ensure_dir_exist
    from analysis.statistics import compute_fmri_stats

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "fmri_stats.tsv"

    if out_file.exists():
        print(f"Skipping run-fmri-stats (output exists: {out_file})")
        return

    ensure_dir_exist(c, "output_data_dir")
    compute_fmri_stats(cneuromod_all_dir, out_file)


@task
def run_fmri_per_subject_stats(c):
    """Compute per-subject fMRI run stats per dataset; save to output_data/fmri_stats_per_subject.tsv."""
    from airoh.utils import ensure_dir_exist
    from analysis.statistics import compute_fmri_stats_per_subject

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "fmri_stats_per_subject.tsv"

    if out_file.exists():
        print(f"Skipping run-fmri-per-subject-stats (output exists: {out_file})")
        return

    ensure_dir_exist(c, "output_data_dir")
    compute_fmri_stats_per_subject(cneuromod_all_dir, out_file)


@task
def run_physio_stats(c):
    """Compute physio recording hours and physprep QC per dataset/subject; save physio_*.tsv."""
    from airoh.utils import ensure_dir_exist
    from analysis.physio import (
        build_physio_run_table,
        compute_physio_stats,
        compute_physio_stats_per_subject,
        crosscheck_declared,
    )

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_files = {
        "runs": output_dir / "physio_runs.tsv",
        "stats": output_dir / "physio_stats.tsv",
        "per_subject": output_dir / "physio_stats_per_subject.tsv",
        "crosscheck": output_dir / "physio_crosscheck.tsv",
    }

    if all(f.exists() for f in out_files.values()):
        print(f"Skipping run-physio-stats (outputs exist in {output_dir})")
        return

    ensure_dir_exist(c, "output_data_dir")
    run_df = build_physio_run_table(cneuromod_all_dir)
    stats = compute_physio_stats(run_df)
    crosscheck = crosscheck_declared(stats, cneuromod_all_dir)
    for scope, df in [
        ("runs", run_df),
        ("stats", stats),
        ("per_subject", compute_physio_stats_per_subject(run_df)),
        ("crosscheck", crosscheck),
    ]:
        df.to_csv(out_files[scope], sep="\t", index=False)
        print(f"Saved {len(df)} rows to {out_files[scope].name}")
    print(crosscheck.to_string(index=False))


def _run_table_datasets(c, dataset):
    """Datasets (with a bids/ tree) selected by --dataset, as a sorted list of names."""
    names = {n.strip() for n in dataset.split(",")} if dataset else None
    return [p.parent.name for p in sorted(_cneuromod_dir(c).glob("*/bids"))
            if names is None or p.parent.name in names]


@task(help={
    "dataset": "Comma-separated dataset names to build tables for (default: all).",
    "subject": "Comma-separated subjects, e.g. sub-01 (default: all with bold runs).",
    "smoke": "Fast minimal run: first dataset (or --dataset), first subject only.",
})
def run_run_tables(c, dataset=None, subject=None, smoke=False):
    """Build run-wise completeness tables, one per dataset x subject (output_data/run_tables/)."""
    import pandas as pd
    from airoh.utils import ensure_dir_exist
    from analysis.run_table import DatasetAssets, build_run_table, run_subjects, table_path
    from analysis.timeseries_index import COLUMNS

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    source_dir = Path(c.config.get("source_data_dir"))
    labels = list(c.config.get("release_remotes", {}))
    atlases = list(c.config.get("timeseries_atlases", []))
    wanted_subjects = {s.strip() for s in subject.split(",")} if subject else None

    datasets = _run_table_datasets(c, dataset)
    if smoke:
        datasets = datasets[:1]
    ts_file = source_dir / "timeseries_index.tsv"
    ts_index = (pd.read_csv(ts_file, sep="\t", keep_default_na=False, dtype={"session": str})
                if ts_file.exists() else pd.DataFrame(columns=COLUMNS))

    ensure_dir_exist(c, "output_data_dir")
    for name in datasets:
        subjects = [s for s in run_subjects(cneuromod_all_dir / name / "bids")
                    if wanted_subjects is None or s in wanted_subjects]
        if smoke:
            subjects = subjects[:1]
        todo = [s for s in subjects if not table_path(output_dir, name, s).exists()]
        if not todo:
            print(f"Skipping run-run-tables for {name} (no tables to build)")
            continue
        assets = DatasetAssets(cneuromod_all_dir, name, source_dir / "annex_locations",
                               ts_index, atlases, labels)
        for sub in todo:
            df = build_run_table(assets, sub)
            out = table_path(output_dir, name, sub)
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out, sep="\t", index=False)
            print(f"Saved {len(df)} rows to {out.relative_to(output_dir)}")


@task
def run_completeness_summary(c):
    """Summarise the run tables per dataset x subject x asset (completeness_summary.tsv, run_tables/index.tsv)."""
    from analysis.run_table import summarize_tables

    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "completeness_summary.tsv"
    index_file = output_dir / "run_tables" / "index.tsv"
    if out_file.exists() and index_file.exists():
        print(f"Skipping run-completeness-summary (output exists: {out_file})")
        return

    summary, index = summarize_tables(output_dir, list(c.config.get("release_remotes", {})))
    summary.to_csv(out_file, sep="\t", index=False)
    index.to_csv(index_file, sep="\t", index=False)
    print(f"Saved {len(summary)} rows to {out_file.name} and {len(index)} tables to {index_file.name}")


@task
def run_dashboard(c):
    """Render output_data/release_dashboard.html (+ release_dashboard_data/) from the run tables."""
    from analysis.dashboard import render_dashboard

    output_dir = Path(c.config.get("output_data_dir"))
    out_html = output_dir / "release_dashboard.html"
    if out_html.exists():
        print(f"Skipping run-dashboard (output exists: {out_html})")
        return
    if not (output_dir / "completeness_summary.tsv").exists():
        print("⚠️  completeness_summary.tsv not found — run `invoke run-completeness-summary` first.")
        return

    render_dashboard(output_dir, Path("dashboard") / "template.html",
                     list(c.config.get("release_remotes", {})), out_html)
    print(f"Saved {out_html.name} (publish it as an Artifact by hand: see README)")


@task
def run_cneuromod_tables(c):
    """Build tidy per-dataset comparison tables from cneuromod.all dataset_info.yaml files."""
    from airoh.utils import ensure_dir_exist
    from analysis.dataset_info import (
        build_cneuromod_maturity_table,
        build_cneuromod_subjects_table,
        build_cneuromod_tidy_table,
        validate_dataset_info,
        COLUMN_GROUPS_PER_SUBJECT,
        COLUMN_GROUPS_TOTAL,
    )

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_files = {
        "per_subject": output_dir / "cneuromod_tidy_per_subject.csv",
        "total": output_dir / "cneuromod_tidy_total.csv",
        "subjects": output_dir / "cneuromod_subjects.csv",
        "maturity": output_dir / "cneuromod_maturity.csv",
    }

    if all(f.exists() for f in out_files.values()):
        print(f"Skipping run-cneuromod-tables (outputs exist in {output_dir})")
        return

    ensure_dir_exist(c, "output_data_dir")
    validate_dataset_info(cneuromod_all_dir, cneuromod_all_dir / "docs" / "schema.json")

    for scope, groups in [
        ("per_subject", COLUMN_GROUPS_PER_SUBJECT),
        ("total", COLUMN_GROUPS_TOTAL),
    ]:
        df = build_cneuromod_tidy_table(cneuromod_all_dir, groups)
        df.to_csv(out_files[scope], index=False)
        print(f"Saved {len(df)} rows to {out_files[scope].name}")

    df = build_cneuromod_subjects_table(cneuromod_all_dir)
    df.to_csv(out_files["subjects"], index=False)
    print(f"Saved {len(df)} rows to {out_files['subjects'].name}")

    df = build_cneuromod_maturity_table(cneuromod_all_dir)
    df.to_csv(out_files["maturity"], index=False)
    print(f"Saved {len(df)} rows to {out_files['maturity'].name}")


@task
def run_cneuromod_summary(c):
    """Aggregate all dataset_info.yaml stats into one CNeuroMod entry (output_data/cneuromod_summary.yaml)."""
    import yaml
    from airoh.utils import ensure_dir_exist
    from analysis.dataset_info import aggregate_cneuromod_summary, validate_dataset_info

    cneuromod_all_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "cneuromod_summary.yaml"

    if out_file.exists():
        print(f"Skipping run-cneuromod-summary (output exists: {out_file})")
        return

    ensure_dir_exist(c, "output_data_dir")
    validate_dataset_info(cneuromod_all_dir, cneuromod_all_dir / "docs" / "schema.json")
    with open(out_file, "w") as f:
        yaml.dump(aggregate_cneuromod_summary(cneuromod_all_dir), f,
                  default_flow_style=False, allow_unicode=True)
    print(f"Saved combined CNeuroMod stats to {out_file.name}")


@task
def run_notebooks(c):
    """Execute notebooks and save figures to output_data/."""
    from airoh.utils import run_notebooks as airoh_run_notebooks, ensure_dir_exist

    notebooks_dir = Path(c.config.get("notebooks_dir"))
    output_dir = Path(c.config.get("output_data_dir")).resolve()

    ensure_dir_exist(c, "output_data_dir")
    airoh_run_notebooks(c, notebooks_dir, output_dir, keys=["source_data_dir", "output_data_dir"])


def _outputs_changed(output_dir):
    """True if git sees changes under output_data/ other than the bookkeeping files."""
    import subprocess
    out = subprocess.run(["git", "status", "--porcelain", "--", str(output_dir)],
                         capture_output=True, text=True).stdout
    return any(Path(line[3:]).name not in ("PROVENANCE.json", "SOURCE_STATE.json")
               for line in out.splitlines())


def _fresh_report(c, dataset=None):
    """(remote heads, stale {dataset: reasons}, code hash) against output_data/SOURCE_STATE.json.

    With `dataset`, exactly those datasets are reported stale.
    """
    from analysis import freshness as fr

    heads = fr.source_heads(_cneuromod_dir(c))
    code = fr.code_hash(".")
    if dataset:
        names = {n.strip() for n in dataset.split(",")}
        return heads, {d: ["requested"] for d in heads if d in names}, code
    state = fr.read_state(c.config.get("output_data_dir"))
    return heads, fr.stale_datasets(heads, state["datasets"], code, state["code_hash"]), code


@task(help={"json": "Print the stale datasets and their reasons as JSON."})
def check_fresh(c, json=False):
    """List datasets whose remote inputs (or the pipeline code) changed since the last refresh. Read-only."""
    import json as jsonlib

    if not _cneuromod_dir(c).is_dir():
        fetch_cneuromod(c)
    _, stale, _ = _fresh_report(c)
    if json:
        print(jsonlib.dumps(stale, indent=2))
        return
    if not stale:
        print("No stale datasets.")
    for name, reasons in stale.items():
        print(f"{name}: {'; '.join(reasons)}")


@task(help={
    "source": "Path to an existing local cneuromod.all checkout to symlink instead of cloning.",
    "dataset": "Comma-separated datasets to treat as stale, regardless of the recorded state.",
    "allow_drop": "Accept a drop in judged runs or remote-held counts for the refreshed datasets.",
})
def refresh(c, source=None, dataset=None, allow_drop=False):
    """Fetch and rebuild only what changed, refusing to record a completeness regression.

    Unlike `fetch` and `run`, this task does both, by design (CI). The cheap
    outputs are always recomputed; the heavy per-dataset part (fmriprep, tsnr,
    timeseries, annex locations, run tables) only for stale datasets, the others
    keeping their committed run tables.
    """
    import pandas as pd
    from airoh.provenance import record_run, record_sources
    from analysis import freshness as fr

    output_dir = Path(c.config.get("output_data_dir"))
    summary_file = output_dir / "completeness_summary.tsv"

    fetch_cneuromod(c, source=source)
    fetch_bids(c)
    fetch_physprep(c)
    heads, stale, code = _fresh_report(c, dataset)
    for name, reasons in stale.items():
        print(f"stale {name}: {'; '.join(reasons)}")
    if not stale:
        print("No stale datasets.")

    before = pd.read_csv(summary_file, sep="\t") if summary_file.exists() else None

    # Cheap tier: always recomputed (run tables, summary and dashboard are handled below).
    for clean_task in (clean_statistics, clean_fmri_stats, clean_fmri_per_subject_stats,
                       clean_physio_stats, clean_cneuromod_tables, clean_cneuromod_summary,
                       clean_figures):
        clean_task(c)
    run_statistics(c)
    run_fmri_stats(c)
    run_fmri_per_subject_stats(c)
    run_physio_stats(c)
    run_cneuromod_tables(c)
    run_cneuromod_summary(c)
    run_notebooks(c)

    # Heavy tier: stale datasets only.
    names = ",".join(sorted(stale))
    if stale:
        fetch_fmriprep(c, dataset=names, strict=True)
        fetch_tsnr(c, dataset=names, strict=True)
        fetch_timeseries(c, dataset=names, strict=True)
        fetch_annex_locations(c, dataset=names)
        fetch_timeseries_index(c, dataset=names)
        record_sources(c)
        for name in sorted(stale):
            clean_run_tables(c, dataset=name)
        run_run_tables(c, dataset=names)
    clean_completeness_summary(c)
    clean_dashboard(c)
    run_completeness_summary(c)
    run_dashboard(c)

    if before is not None and stale and not allow_drop:
        drops = fr.regressions(before, pd.read_csv(summary_file, sep="\t"), list(stale))
        if drops:
            raise SystemExit("Refusing to record a regression (use --allow-drop to accept):\n  "
                             + "\n  ".join(drops))

    if stale:
        recorded = fr.read_state(output_dir)["datasets"]
        recorded.update({d: heads[d] for d in stale})
        fr.write_state(output_dir, code, {d: v for d, v in recorded.items() if d in heads})
    if stale or _outputs_changed(output_dir):
        record_run(c, tasks="refresh")
    print("✅ refresh complete.")


@task(help={"force": "Run `clean` first, forcing every step to recompute."})
def run(c, force=False):
    """Full pipeline."""
    from airoh.provenance import record_run

    if force:
        clean(c)

    run_statistics(c)
    run_fmri_stats(c)
    run_fmri_per_subject_stats(c)
    run_physio_stats(c)
    run_run_tables(c)
    run_completeness_summary(c)
    run_dashboard(c)
    run_cneuromod_tables(c)
    run_cneuromod_summary(c)
    run_notebooks(c)

    record_run(c, tasks="run-statistics,run-fmri-stats,run-fmri-per-subject-stats,"
                        "run-physio-stats,run-run-tables,run-completeness-summary,run-dashboard,run-cneuromod-tables,run-cneuromod-summary,run-notebooks")
    print("Pipeline complete.")


@task(help={
    "skip": "Comma-separated check names to skip (also settable under "
            "`verify: skip_checks:` in invoke.yaml).",
    "strict": "Treat warnings as failures.",
})
def verify(c, skip=None, strict=False):
    """Check that code, config, data and docs still agree. Not part of `run`."""
    from airoh.verify import verify as airoh_verify
    airoh_verify(c, skip=skip, strict=strict)


@task
def run_smoke(c):
    """Smoke test: minimal end-to-end pass."""
    fetch_cneuromod(c)
    fetch_bids(c, strict=True)
    fetch_physprep(c, strict=True)
    run_statistics(c)
    run_fmri_per_subject_stats(c)
    run_physio_stats(c)
    run_run_tables(c, smoke=True)
    run_completeness_summary(c)
    run_cneuromod_tables(c)
    run_cneuromod_summary(c)
    run_notebooks(c)


@task
def clean_fmri_stats(c):
    """Remove fmri_stats.tsv and its JSON sidecar."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "fmri_stats.tsv")
    clean_folder(c, "output_data_dir", "fmri_stats.json")


@task
def clean_fmri_per_subject_stats(c):
    """Remove fmri_stats_per_subject.tsv."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "fmri_stats_per_subject.tsv")


@task
def clean_physio_stats(c):
    """Remove the physio_*.tsv tables."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "physio_*.tsv")


@task(help={"dataset": "Remove only this dataset's tables (and the summaries derived from them)."})
def clean_run_tables(c, dataset=None):
    """Remove the run-wise completeness tables."""
    import shutil
    root = Path(c.config.get("output_data_dir")) / "run_tables"
    shutil.rmtree(root / dataset if dataset else root, ignore_errors=True)
    clean_completeness_summary(c)


@task
def clean_completeness_summary(c):
    """Remove completeness_summary.tsv and the run_tables/index.tsv list."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "completeness_summary.tsv")
    clean_folder(c, "output_data_dir", "run_tables/index.tsv")


@task
def clean_dashboard(c):
    """Remove release_dashboard.html and its data folder."""
    import shutil
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "release_dashboard.html")
    shutil.rmtree(Path(c.config.get("output_data_dir")) / "release_dashboard_data", ignore_errors=True)


@task
def clean_statistics(c):
    """Remove session_counts.tsv."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "session_counts.tsv")


@task
def clean_cneuromod_tables(c):
    """Remove the cneuromod_*.csv comparison tables."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "cneuromod_*.csv")


@task
def clean_cneuromod_summary(c):
    """Remove cneuromod_summary.yaml."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "cneuromod_summary.yaml")


@task
def clean_figures(c):
    """Remove generated figures."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "*.png")


@task
def clean(c):
    """Remove all computed outputs."""
    clean_statistics(c)
    clean_fmri_stats(c)
    clean_fmri_per_subject_stats(c)
    clean_physio_stats(c)
    clean_run_tables(c)
    clean_dashboard(c)
    clean_cneuromod_tables(c)
    clean_cneuromod_summary(c)
    clean_figures(c)


@task
def clean_cneuromod(c):
    """Remove the cneuromod.all checkout (unlink the symlink, or delete a clone)."""
    root = _cneuromod_dir(c)
    if root.is_symlink():
        root.unlink()
        print(f"🧹 Unlinked {root}")
    elif root.is_dir():
        import shutil
        shutil.rmtree(root)
        print(f"🧹 Removed {root}")
    else:
        print(f"🫧 {root} does not exist — nothing to clean")


@task
def clean_source(c):
    """Remove the cneuromod.all checkout."""
    clean_cneuromod(c)
