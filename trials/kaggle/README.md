# Experiments on Kaggle (2x T4)

From 2026-11-26 the owner's decision: "setup all future experiments on this". The local machine has 8 GB of VRAM,
so Inkling's experts sat in RAM, and a case took 22 s at best and 40 to 90 s under memory pressure (E-17d). Kaggle's
free tier gives two T4s (2 x 15 GB), where every model fits on the GPUs at once.

- `build-llama/`: a notebook that builds llama.cpp's server from source at b12627, the tag of the local image
  (`ghcr.io/ggml-org/llama.cpp:server-cuda12-b12627`), for the T4 (sm_75). Run once; its output is attached to every
  job. Rebuild only to change the tag.
- `run.py`: the job notebook. Fetches the model files from Hugging Face (public repos, no token) and checks each
  SHA-256 against the files used locally; starts the servers on the local ports (8081 Inkling, 8082 LFM3, 8083
  d1-2B, 8084 the embedder); clones this repo at the job's commit; fetches TabMWP at 5a1a522 and checks it; runs the
  job's commands; copies its outputs.
- `job.py`: pushes a job from here, waits, and downloads the output into `runs/NAME/` (not committed).

Why not Kaggle's own copies: the Inkling datasets and prebuilt servers there are third-party uploads. Using our own
build and the same files as locally keeps results comparable and the code known.

## Differences from the local runs

- Every model wholly on the GPUs, Inkling split over both by layer. Locally its experts were partly in RAM.
- llama.cpp's default batch sizes for Inkling (locally `-b 512 -ub 128`, to fit 8 GB). Model outputs at temperature 0
  can still differ slightly between builds and GPUs, so a result from Kaggle is compared with a baseline from Kaggle.

## Limits and rules

- 30 GPU hours a week; 12 hours a session, so a job that may run longer is split in chunks. The runners resume from
  their state files, so chunks of one experiment can run in consecutive jobs if the state goes through git.
- Notebooks are private (TabMWP's licence is non-commercial; nothing is published).
- Inputs come only from git at a pushed commit, so every run can be traced to one.
- The token stays in `~/.kaggle/`; nothing in the repo reads or copies it.

## Use

    python3 -I trials/kaggle/job.py e17-smoke --commit $(git rev-parse HEAD) --servers slow,fast \
        --cmd "cd trials/handler-ladder && python3 -I -u smoke.py 20" --out trials/handler-ladder/results

## First benchmark (2026-11-26, job `smoke20`, commit 09afe5f)

`smoke.py 20` on dev1k, all four servers up (GPU memory 10.0 and 14.7 GB of 15.4).

| | Kaggle 2x T4 | local, 8 GB (E-17 smoke) |
| --- | --- | --- |
| correct | 20/20 | 20/20 |
| median s a case | 10.2 | 12.6 |
| mean s a case | 12.0 | 15.8 |
| generation | 15.8 tok/s | 11.6 tok/s |

Same answer strings on 18 of 20. Setup takes about 5.5 minutes a job: fetching and checking the models 208 s
(Inkling, in parallel with the others), loading Inkling 81 s. So Kaggle is about 1.3 times local at its best and
about 4 to 6 times local under the RAM pressure of E-17d (40 to 90 s a case). Not yet tried: the draft model in
Inkling's repo (`dspark-Inkling-2-Mini-Q8_0.gguf`) for speculative decoding.
