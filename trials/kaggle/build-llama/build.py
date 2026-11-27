"""Kaggle: build llama.cpp's server from source at the tag the local runs use (b12627), for T4 (sm_75).

Output, kept by Kaggle as this notebook's output and attached to experiment notebooks as a kernel source:
/kaggle/working/llama/ (llama-server and its shared libraries) and build.json (tag, commit, nvcc version, seconds).
"""
import json, os, shutil, subprocess, time

TAG = "b12627"
t0 = time.time()
run = lambda *a, **k: subprocess.run(list(a), check=True, **k)
run("git", "clone", "--depth", "1", "--branch", TAG, "https://github.com/ggml-org/llama.cpp", "/tmp/llama.cpp")
commit = subprocess.run(["git", "-C", "/tmp/llama.cpp", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
nvcc = subprocess.run(["nvcc", "--version"], capture_output=True, text=True).stdout.strip().splitlines()[-1]
# Kaggle's CUDA 13 image: CMake's FindCUDAToolkit does not find the driver library, so name it (the real one if
# present, else the toolkit's link stub)
import glob
cands = sorted(glob.glob("/usr/lib/x86_64-linux-gnu/libcuda.so*") + glob.glob("/usr/local/nvidia/lib64/libcuda.so*")
               + glob.glob("/usr/local/cuda*/**/stubs/libcuda.so", recursive=True))
print("libcuda candidates:", cands, flush=True)
driver = next((c for c in cands if "stubs" not in c), None) or next(c for c in cands)
run("cmake", "-S", "/tmp/llama.cpp", "-B", "/tmp/build", "-DGGML_CUDA=ON", "-DCMAKE_CUDA_ARCHITECTURES=75",
    "-DLLAMA_CURL=OFF", "-DCMAKE_BUILD_TYPE=Release", f"-DCUDA_cuda_driver_LIBRARY={driver}")
run("cmake", "--build", "/tmp/build", "--target", "llama-server", "-j", str(os.cpu_count()))
out = "/kaggle/working/llama"
os.makedirs(out, exist_ok=True)
for f in os.listdir("/tmp/build/bin"):
    if f == "llama-server" or ".so" in f:
        shutil.copy2(os.path.join("/tmp/build/bin", f), out)
run(os.path.join(out, "llama-server"), "--version", env=dict(os.environ, LD_LIBRARY_PATH=out))
json.dump({"tag": TAG, "commit": commit, "nvcc": nvcc, "seconds": round(time.time() - t0)},
          open("/kaggle/working/build.json", "w"), indent=1)
print(open("/kaggle/working/build.json").read())
