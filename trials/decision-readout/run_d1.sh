#!/bin/sh
# E-04a, part 2: Liquid's open d1 models on every usable case, one after another on the GPU.
set -u
cd "$(dirname "$0")"
wait_up() { for i in $(seq 300); do curl -sf "localhost:$1/health" >/dev/null && return 0; sleep 2; done; return 1; }
for m in d1-omni-600M-GGUF/d1-omni-600M-Q8_0.gguf:d1-omni-600m d1-2B-GGUF/d1-2B-Q8_0.gguf:d1-2b d1-3B-GGUF/d1-3B-Q8_0.gguf:d1-3b; do
  file=${m%%:*}; name=${m##*:}
  ./serve.sh stop
  ./serve.sh d1 "$file" && wait_up 8083 || { echo "$name did not start"; docker logs --tail 20 e04a-d1; continue; }
  python3 -I readout_d1.py --port 8083 --out "results/$name.jsonl" --families 1000
done
./serve.sh stop
echo ALL DONE
