"""E-19: fixed operations filled in by a small model, promoted per operation class on agreement with the large model
(docs/experiments.md, E-19).

E-18's class handlers, written by the large model from 3 examples, matched their examples' wording and raised on new
questions (0 of 250 cases answered cheaply). Here the operations are fixed (`ops.py`) and LFM3 fills in their
arguments for each question (`parse.py`, a JSON schema whose columns are the table's own headers, the class's ops
only). What is learned, per class of E-18's 12 (d1-2B's choice):
- whether the parser may answer: its agreement with the large model on the class's labelled cases where it gave an
  answer (abstaining is free: the case goes to the large model), promoted at E-17d's 95% Wilson lower bound of 0.70 and
  demoted below it;
- its examples: programs that agreed with the large model, the 3 nearest to a new question (by embedding) shown after
  the seed examples.
While a class is active, 1 case in AUDIT_EVERY of those it answers is also sent to the large model, so an active class
can still be demoted.

Two phases, in the stream's fixed order:
- replay (`--replay`): cases 1 to 450, E-18's stream, with E-18's large-model answers as the labels and E-18's classes;
  no large-model calls. Learning only, not measured.
- live (`--chunk 10..12`, 50 cases each): cases 451 to 600, never seen: d1-2B classifies, the parser answers where its
  class is active, the large model everywhere else (and labels).

Gold is never read here. Usage:
    python3 -I stream_v4.py --replay E18_OUT --data DIR --out DIR
    python3 -I stream_v4.py --chunk 10 --data DIR --out DIR
"""
from __future__ import annotations

import argparse, hashlib, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import parse  # noqa: E402
import smoke  # noqa: E402
import smoke_wtq  # noqa: E402
import stream  # noqa: E402
import stream_v2  # noqa: E402
import stream_v3  # noqa: E402
import summarize  # noqa: E402
from wtq_recurrence import coarse_shape  # noqa: E402

REPLAY_N, LIVE_FIRST, TOTAL, CHUNK = 450, 10, 600, 50
AUDIT_EVERY = 5
NEAREST, MAX_EXAMPLES = 3, 200


def lead(a):
    m = re.match(r"\s*(-?\d[\d,]*(?:\.\d+)?)\s*([^\d]*)$", str(a))
    return (float(m.group(1).replace(",", "")), m.group(2).strip()) if m else None


def agree_form(a, b):
    """WTQ's evaluator (`stream_v3.agree`), or the same leading number where the rest of either is only a unit
    ("5" and "5 years", "2.04" and "2.04 seconds"): the large model adds units the table's cells do not."""
    if stream_v3.agree(a, b):
        return True
    x, y = lead(a), lead(b)
    unit = lambda u: u == "" or (len(u) <= 12 and re.fullmatch(r"[a-zA-Z%. ]+", u) is not None)
    return bool(x and y and x[0] == y[0] and unit(x[1]) and unit(y[1]))


def audited(pid):
    return int(hashlib.sha256(pid.encode()).hexdigest(), 16) % AUDIT_EVERY == 0


def table_of(case):
    return {k: [str(x) for x in v] for k, v in (case.get("table_for_pd") or {}).items()}


class StreamV4:
    def __init__(self, data_dir, out_dir, large_fn, small_ask, embed_fn=None, choose_fn=None, log=print, total=TOTAL,
                 k=1, m=1, think_fn=None):
        self.k, self.m, self.think_fn, self._extra = k, m, think_fn, {}
        self.cases = stream.load_cases(data_dir, total)
        self.byid = {c["id"]: c for c in self.cases}
        self.large = stream.Meter(large_fn)
        self.small_ask, self.embed = small_ask, embed_fn or stream_v3.embed_tables
        self.choose = choose_fn or stream_v3.choose_d1
        self.dir, self.log = out_dir, log
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, "state.json")
        self.state = summarize.load(self.path) if os.path.exists(self.path) else {"cases": [], "classes": {}}
        self.done = {r["id"] for r in self.state["cases"]}
        vp = os.path.join(out_dir, "vectors.json")
        self.vectors = summarize.load(vp) if os.path.exists(vp) else {}
        self.small_calls = self.small_seconds = 0

    def save(self):
        for name, obj in (("state.json", self.state), ("vectors.json", self.vectors)):
            p = os.path.join(self.dir, name)
            with open(p + ".tmp", "w") as f:
                json.dump(obj, f)
            os.replace(p + ".tmp", p)
        with open(os.path.join(self.dir, "stream.jsonl.tmp"), "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in self.state["cases"])
        os.replace(os.path.join(self.dir, "stream.jsonl.tmp"), os.path.join(self.dir, "stream.jsonl"))

    def vector(self, pid):
        if pid not in self.vectors:
            self.vectors[pid] = self.embed([self.byid[pid]["question"]])[0]
        return self.vectors[pid]

    def cls_state(self, cls):
        return self.state["classes"].setdefault(cls, {"n": 0, "agree": 0, "abstain": 0, "status": "shadow",
                                                      "promoted_at": None, "demotions": 0, "examples": [],
                                                      "failures": []})

    def examples(self, cls, case):
        ok = parse.allowed(cls)
        seeds = [parse.example_text(*s) for s in sorted(parse.SEEDS, key=lambda s: s[3]["op"] in ok)]
        ex = self.cls_state(cls)["examples"]
        if not ex:
            return seeds
        v = self.vector(case["id"])
        cos = lambda a, b: sum(i * j for i, j in zip(a, b))
        near = sorted(ex, key=lambda e: -cos(v, self.vector(e["id"])))[:NEAREST]
        return seeds + [e["text"] for e in reversed(near)]  # the nearest last

    def run_parser(self, case, cls):
        """k programs (the first greedy); the cheap answer is the largest agreeing group's, if it has m votes or more.
        Every sample is recorded (`samples`), so precision and coverage can be recomputed for any m."""
        t = time.perf_counter()
        try:
            got = parse.samples(case, self.small_ask, self.examples(cls, case), cls, self.k)
        finally:
            self.small_calls += self.k
            self.small_seconds += time.perf_counter() - t
        got = [(stream_v3.strict(a, case) if a is not None else None, p, w) for a, p, w in got]
        voted, votes = parse.vote([a for a, _, _ in got], agree_form)
        prog = next((p for a, p, _ in got if a is not None and voted is not None and agree_form(a, voted)), got[0][1])
        why = got[0][2] if voted is None else "ok"
        self._extra = {"samples": [{"answer": a, "program": p, "why": w} for a, p, w in got], "votes": votes,
                       "voted": voted, "greedy": got[0][0], "seconds_parser": round(time.perf_counter() - t, 3)}
        ans = voted if votes >= self.m else None
        if voted is not None and ans is None:
            why = f"votes {votes} of {self.k}"
        return ans, prog, why

    def think_arm(self, case, cls, label):
        """The comparison arm (not used for promotion): where the greedy program disagrees with the label or gave no
        answer, the same prompt with Inkling thinking first, no practical cap."""
        greedy = self._extra.get("greedy")
        if not self.think_fn or not label or (greedy is not None and agree_form(greedy, label)):
            return None
        t = time.perf_counter()
        text = parse.prompt(case, self.examples(cls, case), cls)
        reply, usage = self.think_fn(text, list(table_of(case)), cls)
        a, p, w = parse.evaluate(case, reply)
        a = stream_v3.strict(a, case) if a is not None else None
        return {"answer": a, "program": p, "why": w, "agreed": a is not None and agree_form(a, label),
                "thinking_tokens": usage.get("thinking_tokens"), "seconds": round(time.perf_counter() - t, 3)}

    def observe(self, cls, case, ans, prog, label):
        c = self.cls_state(cls)
        if not label:
            return None
        if ans is None:
            c["abstain"] += 1
            return None
        ok = agree_form(ans, label)
        c["n"] += 1
        c["agree"] += ok
        if ok:
            t = table_of(case)
            cols = list(t)
            rows = [[t[k][i] for k in cols] for i in range(min(2, len(t[cols[0]]) if cols else 0))]
            c["examples"] = (c["examples"] + [{"id": case["id"], "text": parse.example_text(cols, rows, case["question"], prog)}])[-MAX_EXAMPLES:]
        else:
            c["failures"] = (c["failures"] + [{"id": case["id"], "expected": label, "got": ans, "prog": prog}])[-10:]
        lb = stream_v2.wilson_lower(c["agree"], c["n"])
        if c["status"] == "shadow" and lb >= stream_v2.LOWER:
            c["status"], c["promoted_at"] = "active", len(self.state["cases"])
        elif c["status"] == "active" and lb < stream_v2.LOWER:
            c["status"], c["demotions"] = "shadow", c["demotions"] + 1
        return ok

    def record(self, case, phase, chunk, cls, rung, answer, ans, prog, why, label, ok, large0, small0, route=None):
        rec = {"id": case["id"], "phase": phase, "chunk": chunk, "class": cls, "rung": rung, "answer": answer,
               "parser_answer": ans, "program": prog, "why": why, "label": label, "agreed": ok,
               "audited": rung == "parser" and label is not None, "status_after": self.cls_state(cls)["status"],
               "large": stream.delta(large0, self.large.snap()),
               "small": {"calls": self.small_calls - small0[0], "seconds": round(self.small_seconds - small0[1], 3)},
               "shape": coarse_shape(case), "route": route or {}, **self._extra}
        self.state["cases"].append(rec)
        self.done.add(case["id"])
        self.save()
        return rec

    # ---- replay: E-18's labels, E-18's classes
    def replay(self, e18_out, n=REPLAY_N):
        recs = summarize.jsonl(os.path.join(e18_out, "stream.jsonl"))
        if len(recs) < n:
            raise stream.ChunkError(f"E-18's stream has {len(recs)} of {n} cases")
        e18 = {r["id"]: r for r in recs}
        for case in self.cases[:n]:
            if case["id"] in self.done:
                continue
            r = e18[case["id"]]
            cls = r["class"]
            large0, small0 = self.large.snap(), (self.small_calls, self.small_seconds)
            label = r["answer"] if r["rung"] == "large" and r["answer"] else None
            ans, prog, why = self.run_parser(case, cls)
            self._extra["think"] = self.think_arm(case, cls, label)  # before observe: the case is not yet an example
            ok = self.observe(cls, case, ans, prog, label)
            rec = self.record(case, "replay", r["chunk"], cls, "replay", label, ans, prog, why, label, ok, large0, small0)
            self.log(f"[replay] {len(self.done)} {case['id']} {cls} {self.cls_state(cls)['status']} "
                     f"{'=' if ok else 'x' if ok is False else '-'} {ans!r} / {label!r}")
        return len(self.done)

    # ---- live: fresh cases
    def classify(self, case):
        p = self.choose(case["question"], {f"c{j}": d for j, d in enumerate(stream_v3.CLASSES.values())},
                        stream_v3.CLASS_INSTRUCTIONS)
        best = max(p, key=p.get)
        route = {"class_p": round(p[best], 3)}
        return ("other" if best == "none" or p[best] < stream_v2.D1_MIN else list(stream_v3.CLASSES)[int(best[1:])]), route

    def ask_large(self, case):
        text = self.large.ask(smoke_wtq.prompt(case), stream_v3.LARGE_TOKENS)
        return stream_v3.strict(smoke.extract(text), case) or "", text

    def run_chunk(self, chunk):
        lo = REPLAY_N + (chunk - LIVE_FIRST) * CHUNK
        if chunk < LIVE_FIRST or lo >= len(self.cases):
            raise stream.ChunkError(f"chunk {chunk} is not a live chunk")
        if any(c["id"] not in self.done for c in self.cases[:lo]):
            raise stream.ChunkError("the replay or an earlier chunk is incomplete")
        for case in self.cases[lo:lo + CHUNK]:
            if case["id"] in self.done:
                continue
            large0, small0 = self.large.snap(), (self.small_calls, self.small_seconds)
            cls, route = self.classify(case)
            status = self.cls_state(cls)["status"]
            ans, prog, why = self.run_parser(case, cls)
            label = None
            if status == "active" and ans is not None:
                rung, answer = "parser", ans
                if audited(case["id"]):
                    label, _ = self.ask_large(case)
            else:
                rung = "large"
                answer, _ = self.ask_large(case)
                label = answer
            ok = self.observe(cls, case, ans, prog, label)
            self.record(case, "live", chunk, cls, rung, answer, ans, prog, why, label or None, ok, large0, small0, route)
            self.log(f"[{chunk}] {len(self.done)} {case['id']} {cls} {status} {rung} {answer!r}")
        return lo


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--chunk", type=int)
    g.add_argument("--replay", metavar="E18_OUT")
    ap.add_argument("--parser-url", help="the parser's endpoint (default: the small model's)")
    ap.add_argument("--parser-model", help="its alias (default: the small model's)")
    ap.add_argument("--k", type=int, default=1, help="programs sampled a case (the first greedy)")
    ap.add_argument("--m", type=int, default=1, help="agreeing answers needed for a cheap answer")
    ap.add_argument("--think-arm", action="store_true", help="replay only: the thinking-on comparison arm")
    ap.add_argument("--replay-n", type=int, default=REPLAY_N, help="development only: replay fewer cases")
    stream.add_model_flags(ap)
    a = ap.parse_args()
    large, _ = stream.build_models(a)
    purl, pmodel = a.parser_url or a.small_url, a.parser_model or a.small_model
    small = lambda text, cols, cls, temperature=0, seed=None: parse.ask(text, cols, cls, purl, pmodel, temperature, seed)
    think = (lambda text, cols, cls: parse.ask_thinking(text, cols, cls, purl)) if a.think_arm else None
    s = StreamV4(a.data, a.out, large, small, k=a.k, m=a.m, think_fn=think)
    t = time.time()
    try:
        s.replay(a.replay, a.replay_n) if a.replay else s.run_chunk(a.chunk)
    except stream.ChunkError as e:
        sys.exit(str(e))
    print(f"done in {time.time() - t:.0f} s: large {s.large.snap()} small {s.small_calls} calls {s.small_seconds:.0f} s")
    print(json.dumps({k: {x: v[x] for x in ("n", "agree", "abstain", "status", "promoted_at", "demotions")}
                      for k, v in s.state["classes"].items()}, indent=1))


if __name__ == "__main__":
    main()
