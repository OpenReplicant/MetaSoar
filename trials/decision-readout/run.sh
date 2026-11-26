#!/bin/sh
# E-04a end to end: LFM3 on every usable case, then Inkling on 100 families per slice, one model on the GPU at a time.
set -u
cd "$(dirname "$0")"
mkdir -p results
wait_up() { for i in $(seq 300); do curl -sf "localhost:$1/health" >/dev/null && return 0; sleep 2; done; return 1; }

./serve.sh stop
./serve.sh fast && wait_up 8082 || { echo "fast did not start"; docker logs --tail 20 e04a-fast; exit 1; }
python3 -I readout.py --model fast --port 8082 --out results/lfm3.jsonl --families 1000 \
  --thinking-off '{"chat_template_kwargs": {"enable_thinking": false}}'
./serve.sh stop

./serve.sh slow
if ! wait_up 8081; then
  echo "slow with GPU experts did not start; falling back to CPU-only experts"; docker logs --tail 20 e04a-slow
  docker rm -f e04a-slow
  sed 's/-ngl 999 -ot .blk[^ ]* --no-op-offload/-ngl 0 --no-op-offload/' serve.sh > /tmp/serve-cpu.$$ && sh /tmp/serve-cpu.$$ slow
  wait_up 8081 || { echo "slow did not start"; exit 1; }
fi
python3 -I readout.py --model slow --port 8081 --out results/inkling.jsonl --families 100 \
  --thinking-off '{"reasoning_effort": "none"}'
./serve.sh stop
echo ALL DONE
