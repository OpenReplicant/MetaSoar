"""E-19's parser: the small model fills in an `ops.py` program for a question, under a JSON schema whose column fields
allow only the table's own headers. Examples come first from SEEDS (made-up tables, not WTQ), later from programs that
agreed with the large model on the same class (`examples` argument).

    python3 -I parse.py pilot [N] [DATA_DIR]   (needs LFM3 on :8082; dev1k cases, scored with gold: development only)
"""
from __future__ import annotations

import json, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ops  # noqa: E402

MAX_ROWS, MAX_CHARS, MAX_TOKENS = 40, 5000, 300
ONE = re.compile(r"\s*(name|give|list|tell me|what is|who is|which is)\s+(a|an|one|any)\b", re.I)
CLASS_OPS = {  # the ops a class (stream_v3.CLASSES, chosen by d1-2B) may use; `other` may use all
    "count": ("count", "value", "consecutive"), "superlative": ("argmax", "argmin", "max", "min", "nth"),
    "ordinal": ("nth", "value"), "comparison": ("compare", "argmax", "argmin", "value"),
    "neighbour": ("next", "previous"), "difference": ("difference", "compare"),
    "sum": ("sum", "count"), "average": ("average",), "yes_no": ("exists", "compare"), "list": ("value",),
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
- compare: the "column" value of items[0] against items[1] (or against "than"), found by name in "key"; "direction" is
  greater, less or equal; "answer_as" is yes_no, item (which of the items), or the question's pair of words:
  more_less, above_below, higher_lower, before_after, longer_shorter, older_younger
- consecutive: the longest run of adjacent rows that meet "where" (how many in a row, how many consecutive)
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
    (["Peak", "Height (m)"], [["Ben Alder", "1,148"], ["Ben More", "1,174"]], "Is Ben Alder taller than Ben More?",
     {"op": "compare", "column": "Height (m)", "key": "Peak", "items": ["Ben Alder", "Ben More"], "direction": "greater",
      "answer_as": "yes_no"}),
    (["Peak", "Height (m)"], [["Ben Alder", "1,148"], ["Ben More", "1,174"]], "Is Ben More above or below 1,150 m?",
     {"op": "compare", "column": "Height (m)", "key": "Peak", "items": ["Ben More"], "than": "1150",
      "answer_as": "above_below"}),
    (["Year", "League", "Place"], [["2001", "Div 2", "1st"], ["2002", "Div 1", "4th"]],
     "How many seasons in a row did they play in Div 1?",
     {"op": "consecutive", "column": "Year", "where": [{"column": "League", "is": "=", "value": "Div 1"}]}),
    (["Date", "Tournament", "Outcome"], [["March 2011", "Bern", "Winner"], ["May 2013", "Oslo", "Runner-up"]],
     "How many tournaments took place after 2012?",
     {"op": "count", "column": "Tournament", "where": [{"column": "Date", "is": ">", "value": "2012"}]}),
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


NEEDS_ITEMS = {"neighbour": 1}  # a class whose question names rows must name them (comparison and difference may
# compare an item with a value, so they need one item at least: see `schema`)  # a class whose question names rows must name them
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
        "by": c, "n": {"type": "integer"}, "than": {"type": "string", "maxLength": 40},
        "direction": {"enum": list(ops.DIRECTIONS)}, "answer_as": {"enum": list(ops.ANSWER_AS)}},
        "required": ["op", "column"]}
    if cls in NEEDS_ITEMS:
        k = NEEDS_ITEMS[cls]
        out["properties"]["items"].update(minItems=k, maxItems=k)
        out["required"] += ["key", "items"]
    elif cls in ("comparison", "difference"):
        out["properties"]["items"].update(minItems=1)
        out["required"] += ["key", "items"]
    if THINK:
        out["properties"] = {"thought": {"type": "string", "maxLength": 240}, **out["properties"]}
        out["required"] = ["thought"] + out["required"]
    return out


def guide(cls):
    ok, out, keep = allowed(cls), [], True
    for l in GUIDE.split("\n"):
        if l.startswith("- "):
            keep = any(l.startswith(f"- {o}") for o in ok) or any(f", {o}" in l.split(":")[0] for o in ok)
        elif not l.startswith("  "):
            keep = True
        if keep:
            out.append(l)
    return "\n".join(out)


def prompt(case, examples=None, cls=None):
    ok = allowed(cls)
    seeds = sorted(SEEDS, key=lambda s: s[3]["op"] in ok)  # the class's own ops last, nearest the question
    ex = [example_text(*s) for s in seeds] if examples is None else examples
    return (f"{guide(cls)}\n\nExamples:\n\n" + "\n\n".join(ex) +
            (f"\n\nThis question's operation must be one of: {', '.join(ok)}" if cls in CLASS_OPS else "") +
            f"\n\nTable:\n{show_table(case['table_for_pd'])}\nQuestion: {case['question']}\nProgram:")


EMPTY_THINKING = "<|message_model|><|content_thinking|><|end_message|><|message_model|><|content_text|>"


def _post(url, path, body, timeout=300):
    req = urllib.request.Request(url.rstrip("/") + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


TEMPERATURE = 0.7  # the samples after the first (greedy) one


def ask_no_thinking(text, cols, cls=None, url="http://127.0.0.1:8081", temperature=0, seed=None):
    """Inkling with its thinking closed before it starts: no request switch turns it off (the dev replay: 401 of 450
    replies spent the budget thinking), so the prompt is the chat template's, then an empty thinking block. The
    prompt is cached in the server's slot, so later samples of the same case pay only for their own tokens."""
    prompt = _post(url, "/apply-template", {"messages": [{"role": "user", "content": text}]})["prompt"] + EMPTY_THINKING
    body = {"prompt": prompt, "n_predict": MAX_TOKENS, "temperature": temperature, "cache_prompt": True,
            "json_schema": schema(cols, cls)}
    if seed is not None:
        body["seed"] = seed
    d = _post(url, "/completion", body)
    return d.get("content") or "", {"prompt_tokens": d.get("tokens_evaluated"), "completion_tokens": d.get("tokens_predicted")}


THINK_OPEN = "<|message_model|><|content_thinking|>"
THINK_CLOSE = "<|end_message|><|message_model|><|content_text|>"
THINK_TOKENS = 12000  # no practical cap: the server's context is 16,384


def ask_thinking(text, cols, cls=None, url="http://127.0.0.1:8081"):
    """The comparison arm: Inkling thinks freely (no schema can apply while it thinks), then writes the program under
    the schema after its own end of thinking."""
    base = _post(url, "/apply-template", {"messages": [{"role": "user", "content": text}]})["prompt"] + THINK_OPEN
    t = _post(url, "/completion", {"prompt": base, "n_predict": THINK_TOKENS, "temperature": 0, "cache_prompt": True,
                                   "stop": ["<|end_message|>"]}, timeout=3600)  # ~4,400 tokens at 15 t/s on a T4
    thought = t.get("content") or ""
    d = _post(url, "/completion", {"prompt": base + thought + THINK_CLOSE, "n_predict": MAX_TOKENS, "temperature": 0,
                                   "cache_prompt": True, "json_schema": schema(cols, cls)})
    return d.get("content") or "", {"thinking_tokens": t.get("tokens_predicted"),
                                    "prompt_tokens": d.get("tokens_evaluated"), "completion_tokens": d.get("tokens_predicted")}


def ask(text, cols, cls=None, url="http://127.0.0.1:8082", model="fast", temperature=0, seed=None):
    if model == "slow":
        return ask_no_thinking(text, cols, cls, url, temperature, seed)
    body = {"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": MAX_TOKENS,
            "temperature": temperature, "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"schema": schema(cols, cls)}}}
    if seed is not None:
        body["seed"] = seed
    d = _post(url, "/v1/chat/completions", body)
    return d["choices"][0]["message"].get("content") or "", d.get("usage", {})


def table_of(case):
    return {k: [str(x) for x in v] for k, v in (case.get("table_for_pd") or {}).items()}


def evaluate(case, text):
    """A model's reply -> (answer or None, program or None, why)."""
    table = table_of(case)
    try:
        prog = json.loads(text)
    except ValueError:
        return None, None, "bad json"
    try:
        ans = ops.run(table, prog)
        if ONE.match(case["question"]) and ", " in ans:
            ans = ans.split(", ")[0]  # "name one ...", "give an example of ..."
        return ans, prog, "ok"
    except ops.Unsupported as e:
        return None, prog, f"unsupported: {e}"
    except Exception as e:  # a program the schema allowed but ops did not expect
        return None, prog, f"error: {type(e).__name__}: {e}"


def parse(case, ask_fn, examples=None, cls=None):
    """-> (answer or None, program or None, why). ask_fn(text, cols, cls) -> (content, usage)."""
    table = table_of(case)
    if not table:
        return None, None, "no table"
    text, _ = ask_fn(prompt(case, examples, cls), list(table), cls)
    return evaluate(case, text)


def samples(case, ask_fn, examples=None, cls=None, k=1):
    """k programs for one case: the first greedy, the rest at TEMPERATURE with seeds 1..k-1 (the prompt cached).
    ask_fn(text, cols, cls, temperature, seed) -> (content, usage). -> [(answer, program, why)]."""
    table = table_of(case)
    if not table:
        return [(None, None, "no table")]
    text = prompt(case, examples, cls)
    out = []
    for i in range(k):
        reply, _ = ask_fn(text, list(table), cls, 0 if i == 0 else TEMPERATURE, None if i == 0 else i)
        out.append(evaluate(case, reply))
    return out


def vote(answers, agree):
    """-> (answer, votes): the largest group of agreeing answers (ties: the group holding the first answer)."""
    best, n = None, 0
    for a in answers:
        if a is None:
            continue
        c = sum(1 for b in answers if b is not None and agree(a, b))
        if c > n:
            best, n = a, c
    return best, n


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
        ans, prog, w = parse(case, lambda t, c, k: ask(t, c, k), cls=cls)
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
