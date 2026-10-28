# Source Data

## `cneuromod.all/`

Made available by `invoke fetch-cneuromod`: a symlink to an existing local
checkout (default `../cneuromod.all`, overridable with `--source`), or a
`datalad clone` of [courtois-neuromod/cneuromod.all](https://github.com/courtois-neuromod/cneuromod.all)
when none is found. Either way only the dataset *tree* is retrieved, never
annexed content — the `run-*` tasks only read directory structure,
`*_bold.json` sidecars, physprep `*_desc-quality.json` files, each
dataset's `dataset_info.yaml`, `docs/schema.json` (all plain git files) and the
indexes below. The only annexed content ever opened is a timeseries h5, by
`invoke fetch-timeseries-index`, to list its runs (local copy if present,
otherwise ranged reads from S3; the signals are not downloaded).

Contains one folder per CNeuroMod dataset. Each dataset with a `bids/`
subfolder is itself a Datalad subdataset, installed (tree only) by
`invoke fetch-bids`.

Datasets with a `bids/` subdataset (installed by `fetch-bids`):

- `anat/bids`
- `emotion-videos/bids`
- `floc/bids`
- `friends/bids`
- `gamepad/bids`
- `harrypotter/bids`
- `hcptrt/bids`
- `hearing/bids`
- `langlocalizer/bids`
- `mario/bids`
- `mario3/bids`
- `mario_eeg/bids`
- `mariostars/bids`
- `movie10/bids`
- `multfs/bids`
- `mutemusic/bids`
- `narratives/bids`
- `ood/bids`
- `petit-prince/bids`
- `retinotopy/bids`

Datasets with a `physprep/` subdataset (installed, tree only, by
`invoke fetch-physprep`): `emotion-videos` (empty for now), `friends`,
`harrypotter`, `mario`, `movie10`, `shinobi`. Only their per-run
`*_desc-quality.json` QC files (plain git) are read. Physprep naming drifts
from raw BIDS: movie10 drops the `run-` entity, and harrypotter keeps a stray
`_physio` (`*_physio_desc-quality.json`).

Datasets without a `bids/` folder (metadata accessed differently, TBD):

- `shinobi`
- `things`
- `triplets`

## `annex_locations/`

Written by `invoke fetch-annex-locations`: one `<dataset>_<kind>.tsv` per installed
`bids`, `fmriprep`, `tsnr`, `physprep` and `timeseries` subdataset, with columns `path`,
`key` and `remotes` (the `;`-joined labels from `release_remotes` in `invoke.yaml` that
hold the file). Read from the `git-annex` branch with `git annex whereis`, which merges
`origin/git-annex` in the source checkout, so it only runs at fetch time.

## `timeseries_index.tsv`

Written by `invoke fetch-timeseries-index`: one row per run found inside a timeseries
h5 (`dataset`, `subject`, `atlas`, `key`, `session`, `run_key`, `n_timepoints`). `key`
is the h5's annex key; files whose key is unchanged are not re-read. Git-tracked, since
rebuilding it from S3 is costly. Subject × atlas files that were unreachable (no local
copy and no S3 credentials) have no rows.

## `MANIFEST.json`

Written by `invoke fetch` (see `airoh.provenance.record_sources`): what
`cneuromod.all` actually resolved to (symlink target or clone, size, checksum,
git commit) at fetch time.
