# Source Data

## `cneuromod.all/`

Made available by `invoke fetch-cneuromod`: a symlink to an existing local
checkout (default `../cneuromod.all`, overridable with `--source`), or a
`datalad clone` of [courtois-neuromod/cneuromod.all](https://github.com/courtois-neuromod/cneuromod.all)
when none is found. Either way only the dataset *tree* is retrieved, never
annexed content — this project only reads directory structure,
`*_bold.json` sidecars, each dataset's `dataset_info.yaml` and
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

Datasets without a `bids/` folder (metadata accessed differently, TBD):

- `shinobi`
- `things`
- `triplets`

## `MANIFEST.json`

Written by `invoke fetch` (see `airoh.provenance.record_sources`): what
`cneuromod.all` actually resolved to (symlink target or clone, size, checksum,
git commit) at fetch time.
