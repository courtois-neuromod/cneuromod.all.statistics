# Source Data

## `cneuromod.all/`

Made available by `invoke fetch-cneuromod`: a symlink to an existing local
checkout (default `../cneuromod.all`, overridable with `--source`), or a
`datalad clone` of [courtois-neuromod/cneuromod.all](https://github.com/courtois-neuromod/cneuromod.all)
when none is found. Either way only the dataset *tree* is retrieved, never
annexed content — this project only reads directory structure,
`*_bold.json` sidecars, physprep `*_desc-quality.json` files, each
dataset's `dataset_info.yaml` and
`docs/schema.json`, all plain git files.

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

## `MANIFEST.json`

Written by `invoke fetch` (see `airoh.provenance.record_sources`): what
`cneuromod.all` actually resolved to (symlink target or clone, size, checksum,
git commit) at fetch time.
