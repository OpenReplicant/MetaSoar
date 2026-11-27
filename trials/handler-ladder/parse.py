"""E-19's parser: the small model fills in an `ops.py` program for a question, under a JSON schema whose column fields
allow only the table's own headers. Examples come first from SEEDS (made-up tables, not WTQ), later from programs that
agreed with the large model on the same class (`examples` argument).

    python3 -I parse.py pilot [N] [DATA_DIR]   (needs LFM3 on :8082; dev1k cases, scored with gold: development only)
"""
from __future__ import annotations

import json, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ops  # noqa: E402

MAX_ROWS, MAX_CHARS, MAX_TOKENS = 40, 5000, 300
CLASS_OPS = {  # the ops a class (stream_v3.CLASSES, chosen by d1-2B) may use; `other` may use all
    "count": ("count", "value"), "superlative": ("argmax", "argmin", "max", "min", "nth"), "ordinal": ("nth", "value"),
    "comparison": ("argmax", "argmin", "value"), "neighbour": ("next", "previous"), "difference": ("difference",),
    "sum": ("sum", "count"), "average": ("average",), "yes_no": ("exists",), "list": ("value",),
    "filter": ("value", "argmax", "argmin"), "lookup": ("value", "nth"),
}

GUIDE = """Turn the question into a program that a computer runs on the table. Ops:
- count: how many rows meet the conditions in "where"
- sum, average, max, min: of the numbers in "column", over the rows that meet "where"
- argmax, argmin: the row with the largest or smallest number in "by"; the answer is that row's "column"
- nth: the n-th row (1 first, 2 second, -1 last) in table order, or ranked by "by" (largest first); answer its "column"
- value: the "column" cells of the rows that meet "where" or that "items" names
- next, previous: the row after or before the row that items[0] names in "key"; answer its "column"
- difference: the difference in "column" between the rows items[0] and items[1] name in "key"
- exists: yes or no, whether any row meets "where"
"where" conditions compare a column's cells with a value ("=", "!=", ">", "<", ">=", "<=", "contains"); copy values
exactly as they are written in the table. "items" are row names exactly as written in the "key" column."""

SEEDS = [  # (columns, two rows, question, program): made up, one or two per op
    (["Team", "Wins", "Losses"], [["Hawks", "12", "4"], ["Owls", "9", "7"]], "How many teams won more than 10 games?",
     {"op": "count", "column": "Team", "where": [{"column": "Wins", "is": ">", "value": "10"}]}),
    (["Year", "Album", "Label"], [["2001", "Blue", "Sun"], ["2004", "Red", "Moon"]], "How many albums were released on Sun?",
     {"op": "count", "column": "Album", "where": [{"column": "Label", "is": "=", "value": "Sun"}]}),
    (["Player", "Goals"], [["Ana", "3"], ["Ben", "5"]], "Who scored the most goals?",
     {"op": "argmax", "column": "Player", "by": "Goals"}),
    (["City", "Population"], [["Alton", "12,400"], ["Brill", "8,100"]], "Which city has the smallest population?",
     {"op": "argmin", "column": "City", "by": "Population"}),
    (["Rank", "Name", "Nation"], [["1", "Kim", "Korea"], ["2", "Lee", "Japan"]], "Who was ranked last?",
     {"op": "nth", "column": "Name", "n": -1}),
    (["Date", "Opponent", "Result"], [["May 1", "Lions", "W"], ["May 8", "Bears", "L"]], "Who did they play after the Lions?",
     {"op": "next", "column": "Opponent", "key": "Opponent", "items": ["Lions"]}),
    (["Date", "Opponent", "Result"], [["May 1", "Lions", "W"], ["May 8", "Bears", "L"]], "What was the first game's result?",
     {"op": "nth", "column": "Result", "n": 1}),
    (["Station", "Opened", "Lines"], [["North", "1902", "3"], ["Quay", "1911", "2"]], "When did Quay station open?",
     {"op": "value", "column": "Opened", "where": [{"column": "Station", "is": "=", "value": "Quay"}]}),
    (["Driver", "Team", "Points"], [["Ito", "Arc", "40"], ["Ruiz", "Arc", "31"]], "Which drivers drove for Arc?",
     {"op": "value", "column": "Driver", "where": [{"column": "Team", "is": "=", "value": "Arc"}]}),
    (["Film", "Year", "Gross"], [["Dawn", "1999", "45"], ["Dusk", "2003", "62"]], "How much more did Dusk gross than Dawn?",
     {"op": "difference", "column": "Gross", "key": "Film", "items": ["Dusk", "Dawn"]}),
    (["Film", "Year", "Gross"], [["Dawn", "1999", "45"], ["Dusk", "2003", "62"]], "Which grossed more, Dawn or Dusk?",
     {"op": "argmax", "column": "Film", "by": "Gross", "key": "Film", "items": ["Dawn", "Dusk"]}),
    (["Season", "Games", "Points"], [["2010", "30", "512"], ["2011", "28", "470"]], "How many points in total?",
     {"op": "sum", "column": "Points"}),
    (["Season", "Games", "Points"], [["2010", "30", "512"], ["2011", "28", "470"]], "What was the most games in a season?",
     {"op": "max", "column": "Games"}),
    (["Name", "Country", "Medal"], [["Ola", "Norway", "Gold"], ["Per", "Sweden", "Silver"]],
     "Did anyone from Sweden win a gold medal?",
     {"op": "exists", "column": "Name", "where": [{"column": "Country", "is": "=", "value": "Sweden"},
                                                  {"column": "Medal", "is": "=", "value": "Gold"}]}),
]


def show_table(table, max_rows=MAX_ROWS, max_chars=MAX_CHARS):
    cols = list(table)
    lines = [" | ".join(cols)]
    n = len(table[cols[0]]) if cols else 0
    for i in range(n):
        line = " | ".join(str(table[c][i]) for c in cols)
        if i >= max_rows or sum(map(len, lines)) + len(line) > max_chars:
            lines.append(f"... ({n - i} more rows)")
            break
        lines.append(line)
    return "\n".join(lines)


def example_text(cols, rows, question, prog):
    t = "\n".join([" | ".join(cols)] + [" | ".join(r) for r in rows])
    return f"Table:\n{t}\nQuestion: {question}\nProgram: {json.dumps(prog)}"


NEEDS_ITEMS = {"comparison": 2, "difference": 2, "neighbour": 1}  # a class whose question names rows must name them
THINK = os.environ.get("PARSE_THINK") == "1"


def allowed(cls):
    return CLASS_OPS.get(cls, ops.OPS)


def schema(cols, cls=None):
    c = {"enum": cols}
    out = {"type": "object", "properties": {
        "op": {"enum": list(allowed(cls))}, "column": c,
        "where": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
            "column": c, "is": {"enum": list(ops.CMPS)}, "value": {"type": "string", "maxLength": 80}},
            "required": ["column", "is", "value"]}},
        "key": c, "items": {"type": "array", "maxItems": 2, "items": {"type": "string", "maxLength": 80}},
        "by": c, "n": {"type": "integer"}}, "required": ["op", "column"]}
    if cls in NEEDS_ITEMS:
        k = NEEDS_ITEMS[cls]
        out["properties"]["items"].update(minItems=k, maxItems=k)
        out["required"] += ["key", "items"]
    if THINK:
        out["properties"] = {"thought": {"type": "string", "maxLength": 240}, **out["properties"]}
        out["required"] = ["thought"] + out["required"]
    return out


def guide(cls):
    lines = GUIDE.split("\n")
    ok = allowed(cls)
    return "\n".join(l for l in lines if not l.startswith("- ") or any(l.startswith(f"- {o}") for o in ok)
                     or any(f", {o}" in l.split(":")[0] for o in ok))


def prompt(case, examples=None, cls=None):
    ok = allowed(cls)
    seeds = sorted(SEEDS, key=lambda s: s[3]["op"] in ok)  # the class's own ops last, nearest the question
    ex = [example_text(*s) for s in seeds] if examples is None else examples
    return (f"{guide(cls)}\n\nExamples:\n\n" + "\n\n".join(ex) +
            (f"\n\nThis question's operation must be one of: {', '.join(ok)}" if cls in CLASS_OPS else "") +
            f"\n\nTable:\n{show_table(case['table_for_pd'])}\nQuestion: {case['question']}\nProgram:")


EMPTY_THINKING = "<|message_model|><|content_thinking|><|end_message|><|message_model|><|content_text|>"


def _post(url, path, body):
    req = urllib.request.Request(url.rstrip("/") + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def ask_no_thinking(text, cols, cls=None, url="http://127.0.0.1:8081"):
    """Inkling with its thinking closed before it starts: no request switch turns it off (the dev replay: 401 of 450
    replies spent the budget thinking), so the prompt is the chat template's, then an empty thinking block."""
    prompt = _post(url, "/apply-template", {"messages": [{"role": "user", "content": text}]})["prompt"] + EMPTY_THINKING
    d = _post(url, "/completion", {"prompt": prompt, "n_predict": MAX_TOKENS, "temperature": 0,
                                   "json_schema": schema(cols, cls)})
    return d.get("content") or "", {"prompt_tokens": d.get("tokens_evaluated"), "completion_tokens": d.get("tokens_predicted")}


def ask(text, cols, cls=None, url="http://127.0.0.1:8082", model="fast"):
    if model == "slow":
        return ask_no_thinking(text, cols, cls, url)
    extra = {"chat_template_kwargs": {"enable_thinking": False}}
    body = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": MAX_TOKENS, "temperature": 0,
            **extra,
            "response_format": {"type": "json_schema", "json_schema": {"schema": schema(cols, cls)}}}
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    return d["choices"][0]["message"].get("content") or "", d.get("usage", {})


def parse(case, ask_fn, examples=None, cls=None):
    """-> (answer or None, program or None, why). ask_fn(text, cols, cls) -> (content, usage)."""
    table = {k: [str(x) for x in v] for k, v in (case.get("table_for_pd") or {}).items()}
    if not table:
        return None, None, "no table"
    text, _ = ask_fn(prompt(case, examples, cls), list(table), cls)
    try:
        prog = json.loads(text)
    except ValueError:
        return None, None, "bad json"
    try:
        return ops.run(table, prog), prog, "ok"
    except ops.Unsupported as e:
        return None, prog, f"unsupported: {e}"
    except Exception as e:  # a program the schema allowed but ops did not expect
        return None, prog, f"error: {type(e).__name__}: {e}"


def pilot(n=100, data=os.path.join(HERE, "..", "data", "wtq-84dd647-problems")):
    import collections, random, wtq
    probs = json.load(open(os.path.join(data, "problems_dev1k.json")))
    ids = sorted(probs)
    random.Random(19).shuffle(ids)
    out, why, t = [], collections.Counter(), time.time()
    import stream_v3
    for pid in ids[:n]:
        case = probs[pid]
        p = stream_v3.choose_d1(case["question"], {f"c{j}": d for j, d in enumerate(stream_v3.CLASSES.values())},
                                stream_v3.CLASS_INSTRUCTIONS)
        best = max(p, key=p.get)
        cls = "other" if best == "none" or p[best] < 0.3 else list(stream_v3.CLASSES)[int(best[1:])]
        ans, prog, w = parse(case, ask, cls=cls)
        ok = ans is not None and wtq.correct(ans, case)
        why[w.split(":")[0]] += 1
        out.append({"id": pid, "cls": cls, "q": case["question"], "answer": ans, "gold": case["answer"], "ok": ok, "why": w, "prog": prog})
        print(f"{len(out):3d} {cls[:6]:6} {'+' if ok else '-' if ans else ' '} {case['question'][:70]!r} -> {ans!r} gold {case['answer']} {w[:60]}",
              flush=True)
    answered = [r for r in out if r["answer"] is not None]
    print(f"\n{n} cases in {time.time() - t:.0f} s; answered {len(answered)}, correct {sum(r['ok'] for r in out)} "
          f"({sum(r['ok'] for r in answered) / max(1, len(answered)):.0%} of answered); {dict(why)}")
    for c in sorted({r["cls"] for r in out}):
        rs = [r for r in out if r["cls"] == c]
        a = [r for r in rs if r["answer"] is not None]
        print(f"  {c:12} {len(rs):3d} cases, answered {len(a):3d}, correct {sum(r['ok'] for r in a):3d}")
    json.dump(out, open(os.path.join(HERE, "results", "parse-pilot.json"), "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1:2] == ["pilot"]:
        pilot(int(sys.argv[2]) if len(sys.argv) > 2 else 100, *sys.argv[3:4])
