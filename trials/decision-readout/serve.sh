#!/bin/sh
# Start one llama.cpp server for E-04a, on localhost only, with Substrate's pinned image and model files (S-169).
#   serve.sh fast   LFM3 1.7B Q6_K wholly on the GPU, :8082
#   serve.sh slow   Inkling 2 Mini Q4_K, attention on the GPU and the experts of loop layers 6-12 on the GPU, :8081
#   serve.sh embed  Qwen3-Embedding-0.6B Q8_0 (Apache-2.0), last-token pooling, :8084 (E-04c)
#   serve.sh slow8  as slow, with loop layer 13's experts on the GPU as well (layers 6-13), :8081
#   serve.sh fastcpu  LFM3 1.7B Q6_K on the CPU only, :8082 (beside slow or slow8 on the GPU; E-17)
#   serve.sh ladder   E-17's pair: Inkling with loop layers 6-11 on the GPU (:8081) and LFM3 on the GPU with its KV
#                     cache in RAM (:8082); 13.6 tok/s and 0.4 s an intent call, against 14.5 and 3.0 s with LFM3 on the CPU
#   serve.sh elabcpu  d1-2B (:8083) and the embedder (:8084) on the CPU, beside ladder (E-17d)
#   serve.sh stop   stop all
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
embed)
  # Qwen's official GGUF, revision 370f27d; Qwen3-Embedding pools the last token.
  docker run -d --name e04a-embed $SAFE $GPU -v /home/pete/.lmstudio/models/Qwen/Qwen3-Embedding-0.6B-GGUF:/models:ro \
    -p 127.0.0.1:8084:8080 --entrypoint /app/llama-server $IMG -m /models/Qwen3-Embedding-0.6B-Q8_0.gguf \
    --host 0.0.0.0 --port 8080 --alias embed --embedding --pooling last -ngl 999 -t 2 -c 8192 -b 8192 -ub 8192 ;;
slow8)
  docker run -d --name e04a-slow $SAFE $GPU -v $M/Inkling-2-Mini-Uncensored-GGUF:/models:ro -p 127.0.0.1:8081:8080 \
    --entrypoint /app/llama-server $IMG -m /models/Inkling-2-Mini-Uncensored-AD-Q4_K.gguf --host 0.0.0.0 --port 8080 \
    --alias slow --jinja -ngl 999 -ot 'blk\.([0-5]|1[4-9]|2[0-3])\.ffn_.*_exps.*=CPU' --no-op-offload -t 6 \
    -c 16384 -b 512 -ub 128 -ctk q4_0 -ctv q4_0 -fa on ;;
fastcpu)
  docker run -d --name e04a-fast $SAFE -v $M/LFM3-1.7B-Uncensored-GGUF:/models:ro -p 127.0.0.1:8082:8080 \
    --entrypoint /app/llama-server $IMG -m /models/LFM3-1.7B-Uncensored-AD-Q6_K.gguf --host 0.0.0.0 --port 8080 \
    --alias fast --jinja -ngl 0 -t 8 -c 8192 ;;
ladder)
  docker run -d --name e04a-slow $SAFE $GPU -v $M/Inkling-2-Mini-Uncensored-GGUF:/models:ro -p 127.0.0.1:8081:8080 \
    --entrypoint /app/llama-server $IMG -m /models/Inkling-2-Mini-Uncensored-AD-Q4_K.gguf --host 0.0.0.0 --port 8080 \
    --alias slow --jinja -ngl 999 -ot 'blk\.([0-5]|1[2-9]|2[0-3])\.ffn_.*_exps.*=CPU' --no-op-offload -t 6 \
    -c 16384 -b 512 -ub 128 -ctk q4_0 -ctv q4_0 -fa on
  sleep 60  # Inkling first, so its buffers are placed before LFM3 takes the rest
  docker run -d --name e04a-fast $SAFE $GPU -v $M/LFM3-1.7B-Uncensored-GGUF:/models:ro -p 127.0.0.1:8082:8080 \
    --entrypoint /app/llama-server $IMG -m /models/LFM3-1.7B-Uncensored-AD-Q6_K.gguf --host 0.0.0.0 --port 8080 \
    --alias fast --jinja -ngl 999 -nkvo -t 4 -c 8192 ;;
elabcpu)
  # E-17d's intent elaborator beside `ladder` (the GPU is full): d1-2B (:8083) and Qwen3-Embedding-0.6B (:8084), on
  # the CPU, no GPU devices
  docker run -d --name e04a-d1 $SAFE -v /home/pete/.lmstudio/models/LiquidAI:/models:ro -p 127.0.0.1:8083:8080 \
    --entrypoint /app/llama-server $IMG -m /models/d1-2B-GGUF/d1-2B-Q8_0.gguf --host 0.0.0.0 --port 8080 --alias d1 \
    -ngl 0 -t 4 -c 8192 -b 4096 -ub 4096
  docker run -d --name e04a-embed $SAFE -v /home/pete/.lmstudio/models/Qwen/Qwen3-Embedding-0.6B-GGUF:/models:ro \
    -p 127.0.0.1:8084:8080 --entrypoint /app/llama-server $IMG -m /models/Qwen3-Embedding-0.6B-Q8_0.gguf \
    --host 0.0.0.0 --port 8080 --alias embed --embedding --pooling last -ngl 0 -t 2 -c 4096 -b 4096 -ub 4096 ;;
stop)
  docker rm -f e04a-fast e04a-slow e04a-d1 e04a-embed 2>/dev/null || true ;;
esac
