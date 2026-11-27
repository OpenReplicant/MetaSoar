"""Run an experiment job on Kaggle (2x T4) from here: push, wait, download. See README.md.

    python3 -I trials/kaggle/job.py NAME --commit SHA --servers slow,fast \
        --cmd "cd trials/handler-ladder && python3 -I -u smoke.py 20" --out trials/handler-ladder/results/smoke-dev1k.jsonl

The job runs `run.py` with JOB filled in, as a private notebook `mossmanpete/metasoar-NAME`, with the build notebook
attached. The commit must be pushed: the notebook clones the public repo. Results land in trials/kaggle/runs/NAME/
(not committed; copy what an experiment keeps into its own results folder). Needs the Kaggle CLI (~/.venvs/kaggle)
and its token in ~/.kaggle; nothing here reads the token.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
KAGGLE = os.path.expanduser("~/.venvs/kaggle/bin/kaggle")
USER = "mossmanpete"
BUILD = f"{USER}/metasoar-build-llama-b12627"


def kaggle(*a, check=True):
    r = subprocess.run([KAGGLE, *a], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"kaggle {' '.join(a)}: {r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name")
    ap.add_argument("--commit", required=True)
    ap.add_argument("--servers", default="slow,fast")
    ap.add_argument("--cmd", action="append", required=True)
    ap.add_argument("--out", action="append", default=[])
    ap.add_argument("--timeout", type=int, default=11 * 3600, help="seconds (Kaggle's limit is 12 h a session)")
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args()
    if subprocess.run(["git", "branch", "-r", "--contains", a.commit], capture_output=True, text=True).stdout.strip() == "":
        sys.exit(f"{a.commit} is not on any pushed branch; push it first")
    job = {"name": a.name, "commit": a.commit, "servers": a.servers.split(","), "commands": a.cmd, "outputs": a.out}
    slug = f"{USER}/metasoar-{a.name}"
    with tempfile.TemporaryDirectory() as d:
        src = open(os.path.join(HERE, "run.py")).read().replace("JOB = {}  # written by job.py", f"JOB = {json.dumps(job)}")
        open(os.path.join(d, "run.py"), "w").write(src)
        json.dump({"id": slug, "title": f"metasoar {a.name}", "code_file": "run.py", "language": "python",
                   "kernel_type": "script", "is_private": "true", "enable_gpu": "true", "enable_tpu": "false",
                   "enable_internet": "true", "machine_shape": "", "dataset_sources": [], "competition_sources": [],
                   "kernel_sources": [BUILD], "model_sources": []}, open(os.path.join(d, "kernel-metadata.json"), "w"))
        print(kaggle("kernels", "push", "-p", d, "--accelerator", "NvidiaTeslaT4", "-t", str(a.timeout)).strip())
    if a.no_wait:
        return
    t = time.time()
    while True:
        s = kaggle("kernels", "status", slug, check=False)
        if any(w in s.lower() for w in ("complete", "error", "cancel")):
            break
        time.sleep(60)
    print(s.strip(), f"after {time.time() - t:.0f} s")
    dest = os.path.join(HERE, "runs", a.name)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    kaggle("kernels", "output", slug, "-p", dest, check=False)
    print("output in", dest)


if __name__ == "__main__":
    main()
