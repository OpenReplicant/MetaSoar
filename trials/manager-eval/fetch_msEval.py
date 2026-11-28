#!/usr/bin/env python3
"""Fetch the MS-Eval files this trial reads, pinned to one commit, into data/ (not committed).

Every file is checked against manifest.json (sha256) before it is kept. A file that
does not match is deleted and the script stops. Run with: python3 -I fetch_msEval.py
"""
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "manifest.json")
DEST = os.path.join(HERE, "data", "ms-eval")
BASE = "https://raw.githubusercontent.com/LINs-lab/MS-Eval/{commit}/{path}"


def main():
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    commit = manifest["commit"]
    root = os.path.join(DEST, commit)
    for rel, want in sorted(manifest["files"].items()):
        dst = os.path.join(root, rel)
        if os.path.exists(dst):
            with open(dst, "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() == want:
                    continue
            os.remove(dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with urllib.request.urlopen(BASE.format(commit=commit, path=rel), timeout=60) as r:
            data = r.read()
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            print(f"hash mismatch for {rel}: {got} != {want}; not kept", file=sys.stderr)
            sys.exit(1)
        with open(dst, "wb") as f:
            f.write(data)
    print(f"ok: {len(manifest['files'])} files at {root}")


if __name__ == "__main__":
    main()
