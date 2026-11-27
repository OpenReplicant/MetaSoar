"""Kaggle: run one MetaSoar experiment job on 2x T4. Pushed by `job.py`, which writes JOB below; not run locally.

1. llama-server from the build notebook (`build-llama/`, llama.cpp b12627 built from source), attached as a kernel
   source.
2. The model files the local runs use, from Hugging Face (public repos, no token), checked against their SHA-256.
3. The servers on the local ports (8081 Inkling, 8082 LFM3, 8083 d1-2B, 8084 the embedder): every model wholly on
   the GPUs, Inkling split over both. The flags are the local ones (`trials/decision-readout/serve.sh`), less the
   offloading that 8 GB needed.
4. MetaSoar cloned at the job's commit (public repo); TabMWP fetched at 5a1a522 and checked.
5. The job's commands, in order, from the repo root; then the job's outputs, the server logs and timings copied to
   /kaggle/working/out/, which `job.py` downloads.
"""
import glob, hashlib, json, os, shutil, subprocess, sys, threading, time, urllib.request

JOB = {}  # written by job.py

T0 = time.time()
OUT = "/kaggle/working/out"
MODELS = "/kaggle/tmp/models"
REPO = "/kaggle/tmp/MetaSoar"
os.makedirs(OUT, exist_ok=True)
os.makedirs(MODELS, exist_ok=True)
times = {}


def log(*a):
    print(f"[{time.time() - T0:7.0f}s]", *a, flush=True)


HF = {  # name: (repo, file, sha256) -- the files under ~/.lmstudio/models locally, same sizes
    "inkling": ("AtomicChat/Inkling-2-Mini-Uncensored-GGUF", "Inkling-2-Mini-Uncensored-AD-Q4_K.gguf",
                "36e99f1f56ca33cb356f19d7e3822938f65af1cde978ad13170238928d4c955f"),
    "lfm3": ("AtomicChat/LFM3-1.7B-Uncensored-GGUF", "LFM3-1.7B-Uncensored-AD-Q6_K.gguf",
             "4a7d91c094b9a0f8ed094093f3a0eb3cfeeb46b9bd491e33115689fc5d658b22"),
    "d1": ("LiquidAI/d1-2B-GGUF", "d1-2B-Q8_0.gguf", "073313d92b53b0ac8193db6e906cb3c78a98183d244b15b7b8f5426115c6738c"),
    "embed": ("Qwen/Qwen3-Embedding-0.6B-GGUF", "Qwen3-Embedding-0.6B-Q8_0.gguf",
              "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439"),
    "dspark": ("AtomicChat/Inkling-2-Mini-Uncensored-GGUF", "dspark-Inkling-2-Mini-Q8_0.gguf",
               "f51f32d3fb4dca9ca2f094e447b80741caac0a3445ec02af02a8cc3c86e45992"),
}
SERVERS = {  # name: (model, port, CUDA devices, flags). Inkling first, placed by llama.cpp's fit with margins
    # left for the others: about 4 GB on GPU 0 (LFM3, the embedder) and 3 GB on GPU 1 (d1-2B)
    "slow": ("inkling", 8081, "0,1", "--alias slow --jinja -sm layer -fitt 4096,3072 -c 16384 -ctk q4_0 -ctv q4_0 -fa on -t 4"),
    "fast": ("lfm3", 8082, "0", "--alias fast --jinja -ngl 999 -c 8192 -fa on -ctk q8_0 -ctv q8_0 -t 2"),
    "d1": ("d1", 8083, "1", "--alias d1 -ngl 999 -c 16384 -b 8192 -ub 8192 -t 2"),
    "embed": ("embed", 8084, "0", "--alias embed --embedding --pooling last -ngl 999 -c 8192 -b 8192 -ub 8192 -t 2"),
    # Inkling with its DSpark drafter (speculative decoding, as the model card runs it); serves as "slow" on 8081.
    # Greedy outputs can differ from plain decoding (the card says so), so it needs its own baseline.
    "slow-dspark": ("inkling", 8081, "0,1", "--alias slow --jinja -sm layer -fitt 4096,4096 -c 16384 -ctk q4_0 -ctv q4_0 "
                    "-fa on -t 4 -md @dspark --spec-type draft-dspark --spec-draft-n-max 3 -ngld 99"),
}
EXTRA = {"slow-dspark": ["dspark"]}  # further model files a server needs, named in its flags as @name
TABMWP = {"problems_test1k.json": "bf34a84d359c48ba", "problems_dev1k.json": "e8a3acdb3726c7ab"}  # sha256 prefixes


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def fetch(name):
    repo, fname, want = HF[name]
    path = os.path.join(MODELS, fname)
    t = time.time()
    subprocess.run(["curl", "-sSfL", "--retry", "5", "-o", path, f"https://huggingface.co/{repo}/resolve/main/{fname}"],
                   check=True)
    got = sha256(path)
    if got != want:
        raise SystemExit(f"{fname}: sha256 {got}, expected {want}")
    times[f"fetch {name}"] = round(time.time() - t)
    log("fetched and checked", fname, f"{os.path.getsize(path) / 1e9:.1f} GB")


def main():
    log("job", json.dumps(JOB))
    subprocess.run(["nvidia-smi"], check=False)
    need = {SERVERS[s][0] for s in JOB["servers"]} | {m for s in JOB["servers"] for m in EXTRA.get(s, [])}
    threads = [threading.Thread(target=fetch, args=(m,)) for m in need]
    for t in threads:
        t.start()

    t = time.time()
    subprocess.run(["git", "clone", "-q", "https://github.com/OpenReplicant/MetaSoar", REPO], check=True)
    subprocess.run(["git", "-C", REPO, "checkout", "-q", JOB["commit"]], check=True)
    data = os.path.join(REPO, "trials", "data", "tabmwp-5a1a522")
    os.makedirs(data, exist_ok=True)
    for f, want in TABMWP.items():
        p = os.path.join(data, f)
        urllib.request.urlretrieve(f"https://raw.githubusercontent.com/lupantech/PromptPG/5a1a522/data/tabmwp/{f}", p)
        assert sha256(p).startswith(want), f
    times["clone and data"] = round(time.time() - t)
    for t in threads:
        t.join()

    built = os.path.dirname(glob.glob("/kaggle/input/**/llama-server", recursive=True)[0])
    llama = "/kaggle/tmp/llama"  # inputs are mounted read-only, so copy before marking it executable
    shutil.copytree(built, llama, dirs_exist_ok=True)
    os.chmod(os.path.join(llama, "llama-server"), 0o755)
    subprocess.run([os.path.join(llama, "llama-server"), "--list-devices"], env=dict(os.environ, LD_LIBRARY_PATH=llama))
    procs = []
    for s in JOB["servers"]:
        model, port, dev, flags = SERVERS[s]
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=dev, LD_LIBRARY_PATH=llama)
        f = open(os.path.join(OUT, f"server-{s}.log"), "w")
        procs.append(subprocess.Popen([os.path.join(llama, "llama-server"), "-m", os.path.join(MODELS, HF[model][1]),
                                       "--host", "127.0.0.1", "--port", str(port),
                                       *[os.path.join(MODELS, HF[x[1:]][1]) if x.startswith("@") else x for x in flags.split()]],
                                      env=env, stdout=f, stderr=subprocess.STDOUT))
        t = time.time()
        while True:  # one at a time, so each places its buffers before the next
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
                    if b"ok" in r.read():
                        break
            except Exception:
                pass
            if procs[-1].poll() is not None:
                raise SystemExit(f"server {s} exited; see server-{s}.log")
            time.sleep(3)
        times[f"load {s}"] = round(time.time() - t)
        log("server up", s, port)
    subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv"], check=False)

    rc = 0
    for cmd in JOB["commands"]:
        t = time.time()
        log("run", cmd)
        r = subprocess.run(cmd, shell=True, cwd=REPO)
        times[f"cmd {cmd[:60]}"] = round(time.time() - t)
        if r.returncode:
            rc = r.returncode
            log("command failed", r.returncode)
            break
    for p in JOB["outputs"]:
        src = os.path.join(REPO, p)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(OUT, p), dirs_exist_ok=True)
        elif os.path.exists(src):
            os.makedirs(os.path.dirname(os.path.join(OUT, p)), exist_ok=True)
            shutil.copy2(src, os.path.join(OUT, p))
    for p in procs:
        p.terminate()
    times["total"] = round(time.time() - T0)
    json.dump({"job": JOB, "seconds": times, "returncode": rc}, open(os.path.join(OUT, "job.json"), "w"), indent=1)
    log("done", json.dumps(times))
    sys.exit(rc)


main()
