"""The cartographer: maps an organization from its workspace (envkit/org.py), and asks its principal only what the
record can't settle. Claims, each with its evidence:

- **actors**: commits, repositories, days active, the sessions their work came from, whom they worked alongside
  (co-authors); an actor whose commits come from sessions works as an agent.
- **repositories**: what each says it is, how active it has been and when, which areas of it change, who works on
  it; repositories worked on by the same actor on the same day are **linked** (counted).
- **eras**: the repositories that took most of the work, month by month.
- **who the principal is**: not in the record (an organization's account, a person's names, agents): asked.

Interviews are exploration, with a cost: the principal's attention. Each run may ask `budget` questions, chosen by
how much of the map hangs on the answer: who the principal is first (it decides whose goals and whose work is
whose), then what the strongest links are, then what repositories with no clear description are for, then whether
dormant ones are done. A question is asked once; its answer, when given, becomes a claim with the principal as its
source and replaces the guess.
"""
from __future__ import annotations

import collections
import datetime as dt

DAY = 86400
VAGUE = 40  # a description shorter than this says too little


def day_str(d):
    return dt.date.fromtimestamp(d * DAY).isoformat()


class Cartographer:
    def __init__(self, names, budget=4, seed=0):
        self.names, self.budget = list(names), budget
        self.actors = collections.defaultdict(lambda: {"commits": 0, "repos": collections.Counter(), "first": None,
                                                        "last": None, "sessions": set(), "with": collections.Counter()})
        self.repos = {}
        self.month = collections.defaultdict(collections.Counter)  # "YYYY-MM" -> repo -> commits
        self.links = collections.Counter()  # (repo, repo) -> days some author worked on both
        self.day_work = collections.defaultdict(set)  # (day, actor) -> repos
        self.areas = collections.defaultdict(collections.Counter)
        self.asked, self.answers, self.queue = {}, {}, []
        self.principal, self.day, self.why = None, None, ""
        self.d0, self.until = 0, None
        self.seen = set()

    # --- reading the workspace ----------------------------------------------------------------------------------
    def read(self, state):
        for e in state["entries"]:
            k, a = e["key"], e["attrs"]
            if e["kind"] == "repo":
                r = self.repos.setdefault(k.split(":", 1)[1], {"commits": 0, "first": None, "last": None})
                r["description"], r["fork"] = a.get("description", ""), a.get("fork")
            elif e["kind"] == "commit" and k not in self.seen:
                self.seen.add(k)
                self.event(a)
            elif e["kind"] == "event" and a.get("kind") == "start":
                self.d0, self.until = a["day"], a.get("until")
            elif e["kind"] == "reply" and a["id"] not in self.answers:
                self.answers[a["id"]] = a
                self.answered(a)

    def event(self, c):
        d, repo = c["t"] // DAY, c["repo"]
        r = self.repos.setdefault(repo, {"description": "", "fork": False, "commits": 0, "first": None, "last": None})
        r["commits"] += 1
        r["first"] = d if r["first"] is None else min(r["first"], d)
        r["last"] = d if r["last"] is None else max(r["last"], d)
        self.month[day_str(d)[:7]][repo] += 1
        for area in c.get("areas", []):
            self.areas[repo][area] += 1
        for who in [c["author"]] + c.get("coauthors", []):
            x = self.actors[who]
            x["commits"] += who == c["author"]
            x["repos"][repo] += 1
            x["first"] = d if x["first"] is None else min(x["first"], d)
            x["last"] = d if x["last"] is None else max(x["last"], d)
            if c.get("session") and who == c["author"]:
                x["sessions"].add(c["session"])
            for other in [c["author"]] + c.get("coauthors", []):
                if other != who:
                    x["with"][other] += 1
        key = (d, c["author"])
        if repo not in self.day_work[key]:
            for other_repo in self.day_work[key]:
                self.links[tuple(sorted((repo, other_repo)))] += 1  # once per day and pair
            self.day_work[key].add(repo)

    # --- claims --------------------------------------------------------------------------------------------------
    def agents(self):
        return {n for n, x in self.actors.items() if len(x["sessions"]) >= 3}

    def assistants(self):
        """Names that only ever appear as co-authors: something working with whoever made the commit (a tool, a
        model behind an agent), not an actor of its own."""
        return {n for n, x in self.actors.items() if x["commits"] == 0}

    def people(self):
        return sorted((n for n in self.actors if n not in self.agents() and n not in self.assistants()),
                      key=lambda n: -self.actors[n]["commits"])

    def answered(self, a):
        q = self.asked.get(a["id"], {})
        text = a.get("answer", "")
        if q.get("about") == "principal":
            named = [n for n in self.actors if n.lower() in text.lower()]
            self.principal = named or None
        elif q.get("about", "").startswith("repo:"):
            self.repos.setdefault(q["about"][5:], {}).update({"purpose": text})
        elif q.get("about", "").startswith("link:"):
            self.link_notes = getattr(self, "link_notes", {})
            self.link_notes[q["about"][5:]] = text

    def candidates(self):
        """Questions worth the principal's attention now, most consequential first: (priority, about, question)."""
        out = []
        if self.principal is None and len(self.people()) >= 2:
            ppl = self.people()
            out.append((0, "principal", f"Which of these identities are you (or act for you): {', '.join(ppl)}? "
                                        f"The history can't tell an organization's account from a person's."))
        for (a, b), n in self.links.most_common(2):
            if n >= 5:
                out.append((1, f"link:{a}+{b}", f"{a} and {b} were worked on the same days {n} times. How does one "
                                                f"depend on or feed the other?"))
        for name, r in sorted(self.repos.items()):
            if r.get("commits") and len(r.get("description", "")) < VAGUE and "purpose" not in r:
                out.append((2, f"repo:{name}", f"What is {name} for? It describes itself as "
                                               f"{r.get('description') or 'nothing'!r}."))
        if self.day is not None:
            for name, r in sorted(self.repos.items()):
                if r.get("last") is not None and self.day - r["last"] > 365 and r.get("commits", 0) >= 5:
                    out.append((3, f"dormant:{name}", f"{name} has had no commits since {day_str(r['last'])}. "
                                                      f"Done, archived, or waiting?"))
        return sorted(out)

    # --- acting --------------------------------------------------------------------------------------------------
    def step(self, obs):
        state = obs["state"]
        self.read(state)
        self.day = self.d0 + state["t"]
        caught_up = self.until is None or self.day >= self.until  # a replay: read the history first, then ask
        if caught_up and len(self.asked) < self.budget:
            for _, about, question in self.candidates():
                from envkit.org import qid
                q = qid("principal", question)
                if q in self.asked or any(v["about"] == about for v in self.asked.values()):
                    continue
                self.asked[q] = {"about": about, "question": question}
                self.why = f"asking the principal about {about}"
                return "interview", {"who": "principal", "question": question, "why": about}
        self.why = "reading"
        return "wait", None

    def posts(self):
        if self.principal and not getattr(self, "_posted_p", None):
            self._posted_p = True
            return [{"key": "claim:principal", "kind": "claim", "source": "cartographer", "salience": 1.0,
                     "attrs": {"actors": self.principal}}]
        return None

    # --- the map -------------------------------------------------------------------------------------------------
    def report(self):
        agents, L = self.agents(), []
        L.append("# OpenReplicant, as mapped from its history\n")
        who = ", ".join(self.principal) if self.principal else "not known yet (asked)"
        L.append(f"**Principal:** {who}\n")
        L.append("## Actors\n")
        L.append("| actor | works as | commits | days active | repositories (most first) | alongside |")
        L.append("|---|---|---|---|---|---|")
        for n, x in sorted(self.actors.items(), key=lambda kv: -kv[1]["commits"]):
            if x["commits"] == 0 and not x["with"]:
                continue
            role = (f"agent ({len(x['sessions'])} sessions)" if n in agents else
                    "principal" if self.principal and n in self.principal else
                    "assistant (co-author only)" if n in self.assistants() else "person or account")
            L.append(f"| {n} | {role} | {x['commits']} | {day_str(x['first'])} to {day_str(x['last'])} | "
                     f"{', '.join(f'{r} {c}' for r, c in x['repos'].most_common(4))} | "
                     f"{', '.join(f'{o} {c}' for o, c in x['with'].most_common(2)) or '-'} |")
        L.append("\n## Repositories\n")
        L.append("| repository | says it is | commits | active | changes most in |")
        L.append("|---|---|---|---|---|")
        for name, r in sorted(self.repos.items(), key=lambda kv: -(kv[1].get("last") or 0)):
            if not r.get("commits"):
                continue
            desc = r.get("purpose") or r.get("description") or "-"
            L.append(f"| {name}{' (fork)' if r.get('fork') else ''} | {desc[:90]} | {r['commits']} | "
                     f"{day_str(r['first'])} to {day_str(r['last'])} | "
                     f"{', '.join(a for a, _ in self.areas[name].most_common(4))} |")
        L.append("\n## Linked repositories (same actor, same day)\n")
        for (a, b), n in self.links.most_common(8):
            note = getattr(self, "link_notes", {}).get(f"{a}+{b}")
            L.append(f"- {a} and {b}: {n} days" + (f" (principal: {note})" if note else ""))
        L.append("\n## Eras (where the work went, by month)\n")
        for m in sorted(self.month):
            top = self.month[m].most_common(3)
            L.append(f"- {m}: " + ", ".join(f"{r} {c}" for r, c in top))
        L.append("\n## Asked of the principal\n")
        for q, v in self.asked.items():
            a = self.answers.get(q)
            L.append(f"- {v['question']}\n  - " + (f"answer: {a['answer']}" if a else "not answered yet"))
        return "\n".join(L) + "\n"
