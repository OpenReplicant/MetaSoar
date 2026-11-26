#!/bin/sh
# Start one llama.cpp server for E-04a, on localhost only, with Substrate's pinned image and model files (S-169).
#   serve.sh fast   LFM3 1.7B Q6_K wholly on the GPU, :8082
#   serve.sh slow   Inkling 2 Mini Q4_K, attention on the GPU and the experts of loop layers 6-12 on the GPU, :8081
#   serve.sh stop   stop both
set -eu
IMG=ghcr.io/ggml-org/llama.cpp:server-cuda12-b12627
L=/usr/lib/x86_64-linux-gnu
M=/home/pete/.lmstudio/models/AtomicChat
GPU="--device /dev/nvidia0 --device /dev/nvidiactl --device /dev/nvidia-uvm --device /dev/nvidia-uvm-tools
 -v $L/libcuda.so.1:$L/libcuda.so.1:ro -v $L/libcuda.so.1:$L/libcuda.so:ro
 -v $L/libnvidia-ml.so.1:$L/libnvidia-ml.so.1:ro -v $L/libnvidia-ptxjitcompiler.so.1:$L/libnvidia-ptxjitcompiler.so.1:ro"
SAFE="--cap-drop ALL --security-opt no-new-privileges:true"
case "$1" in
fast)
  docker run -d --name e04a-fast $SAFE $GPU -v $M/LFM3-1.7B-Uncensored-GGUF:/models:ro -p 127.0.0.1:8082:8080 \
    --entrypoint /app/llama-server $IMG -m /models/LFM3-1.7B-Uncensored-AD-Q6_K.gguf --host 0.0.0.0 --port 8080 \
    --alias fast --jinja -ngl 999 -t 2 -c 32768 -fa on -ctk q8_0 -ctv q8_0 ;;
slow)
  # Inkling has 24 blocks; 6-17 loop three times per token, so their experts gain most from the GPU.
  # Op offload off: with experts in RAM it asks for 7-9 GB of compute buffer (S-169).
  docker run -d --name e04a-slow $SAFE $GPU -v $M/Inkling-2-Mini-Uncensored-GGUF:/models:ro -p 127.0.0.1:8081:8080 \
    --entrypoint /app/llama-server $IMG -m /models/Inkling-2-Mini-Uncensored-AD-Q4_K.gguf --host 0.0.0.0 --port 8080 \
    --alias slow --jinja -ngl 999 -ot 'blk\.([0-5]|1[3-9]|2[0-3])\.ffn_.*_exps.*=CPU' --no-op-offload -t 6 \
    -c 16384 -b 512 -ub 128 -ctk q4_0 -ctv q4_0 -fa on ;;
d1)
  # Liquid's open d1 decision models (LFM Open License v1.0), served on llama.cpp's native /v1/systemone endpoint
  # (b11960 or later). A question is read in one batch, so -b and -ub must hold the whole state.
  #   serve.sh d1 d1-2B-GGUF/d1-2B-Q8_0.gguf
  docker run -d --name e04a-d1 $SAFE $GPU -v /home/pete/.lmstudio/models/LiquidAI:/models:ro -p 127.0.0.1:8083:8080 \
    --entrypoint /app/llama-server $IMG -m "/models/$2" --host 0.0.0.0 --port 8080 --alias d1 \
    -ngl 999 -t 2 -c 16384 -b 8192 -ub 8192 ;;
stop)
  docker rm -f e04a-fast e04a-slow e04a-d1 2>/dev/null || true ;;
esac
