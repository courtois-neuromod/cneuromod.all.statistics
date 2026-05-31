# Source Data

## `cneuromod.all/` (git submodule)

A git submodule pointing to [courtois-neuromod/cneuromod.all](https://github.com/courtois-neuromod/cneuromod.all).

Contains one folder per CNeuroMod dataset. Each dataset with a `bids/` subfolder is itself a sub-submodule, initialized by `invoke fetch` (non-recursive — no datalad, no further nesting).

Datasets with a `bids/` sub-submodule (initialized by `fetch`):

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
