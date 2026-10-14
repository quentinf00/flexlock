# OmniHAFS TODO

## Goal
TC wind field forecaster from partial and noisy observations (speed-only or full vector)
using a Perceiver IO architecture on HAFS forecast sequences.

## Done
- [x] `src/sample_project/data/loader_hafs.py` — WebDataset sequence loader (train/val)
- [x] `src/sample_project/perceiver/model.py` — HAFSPerceiverForecaster (2-modality Perceiver IO)
- [x] `src/sample_project/perceiver/train.py` — @flexcli training (mixed/speed/vector scenarios)
- [x] `configs/defaults.py` — HAFS perceiver stage templates (base, speed, vector, noisy, dense)
- [x] `pipeline.py` — hafs_base / hafs_sweep experiment recipes
- [x] `pyproject.toml` — added webdataset dependency
- [x] Removed SSH-specific modules (preprocess.py, preprocess_glorys.py, merge.py, reconstruct.py, assimilate.py)

## Next: install & smoke test
- [ ] `pixi install` to resolve webdataset lock
- [ ] Smoke test loader: verify `(B, 28, 2, 200, 250)` batch loads cleanly from val shards
- [ ] Smoke test model: forward pass with random obs + query coords, check `(B, P, 2)` output
- [ ] 1-epoch training run on 1 GPU, confirm loss decreases

## Next: evaluation
- [ ] `src/sample_project/perceiver/eval.py` — validation loop computing RMSE per horizon
- [ ] Decode predicted (u, v) back to physical units (undo z-score), compute wind speed RMSE
- [ ] Visualize: predicted vs GT wind field at t+1day, t+3day, t+7day
- [ ] Compare scenarios: speed_only vs vector vs mixed at same n_obs

## Next: inference / assimilation
- [ ] `src/sample_project/perceiver/sample.py` — probabilistic inference via MC Dropout or
      ensemble (train N models with different obs seeds) for uncertainty estimation
- [ ] Guidance / conditioning: given real satellite wind speed obs, produce full vector forecast

## Stretch
- [ ] Multi-step: use Perceiver output at t+horizon as new obs → auto-regressive rollout
- [ ] Cross-storm generalization: evaluate on held-out storm categories
- [ ] Joint speed+direction via FiLM modulation on the latent array
