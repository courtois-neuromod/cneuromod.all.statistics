from pathlib import Path
from invoke import task


@task
def fetch(c):
    """Init cneuromod.all submodule and each dataset's bids sub-submodule."""
    submodule_path = Path("source_data/cneuromod.all")

    print("Updating cneuromod.all submodule...")
    c.run("git submodule update --init source_data/cneuromod.all")

    for bids_dir in sorted(submodule_path.glob("*/bids")):
        rel = bids_dir.relative_to(submodule_path)
        dataset = bids_dir.parent.name
        print(f"Initializing {dataset}/bids...")
        c.run(f"git -C source_data/cneuromod.all submodule update --init {rel}")


@task
def run_statistics(c):
    """Count sessions per subject per dataset; save to output_data/session_counts.tsv."""
    from airoh.utils import ensure_dir_exist
    from analysis.statistics import count_sessions

    source_dir = Path(c.config.get("source_data_dir"))
    output_dir = Path(c.config.get("output_data_dir"))
    out_file = output_dir / "session_counts.tsv"

    if out_file.exists():
        print(f"Skipping run-statistics (output exists: {out_file})")
        return

    ensure_dir_exist(c, "output_data_dir")
    count_sessions(source_dir, out_file)


@task
def run_notebooks(c):
    """Execute notebooks and save figures to output_data/."""
    from airoh.utils import run_notebooks as airoh_run_notebooks, ensure_dir_exist

    notebooks_dir = Path(c.config.get("notebooks_dir"))
    output_dir = Path(c.config.get("output_data_dir")).resolve()

    ensure_dir_exist(c, "output_data_dir")
    airoh_run_notebooks(c, notebooks_dir, output_dir, keys=["source_data_dir", "output_data_dir"])


@task(pre=[fetch, run_statistics, run_notebooks])
def run(c):
    """Full pipeline."""
    print("Pipeline complete.")


@task
def run_smoke(c):
    """Smoke test: minimal end-to-end pass."""
    fetch(c)
    run_statistics(c)
    run_notebooks(c)


@task
def clean_statistics(c):
    """Remove session_counts.tsv."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "session_counts.tsv")


@task
def clean_figures(c):
    """Remove generated figures."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "*.png")


@task(pre=[clean_statistics, clean_figures])
def clean(c):
    """Remove all computed outputs."""
    pass


@task
def clean_source(c):
    """Deinitialize the cneuromod.all submodule and all bids sub-submodules."""
    c.run("git submodule deinit -f source_data/cneuromod.all")
