"""
play.py — The Reconciliation Game, in a terminal.

    python3 play.py                    score your policy.json
    python3 play.py --watch            re-score every time you save it
    python3 play.py --pkg PKG-008      one package, field by field
    python3 play.py --compare          the reference policies
    python3 play.py --hint             what each package is testing
    python3 play.py --resilience       your policy at four failure rates

Standard library only. No pip, no network, works on a locked-down machine.

THE LOOP THAT MATTERS is --watch. Split your editor: policy.json on the left,
this on the right. Change a number, save, and the score moves before you have
looked back up. Under a second and people experiment; over five and they start
planning instead, which is a slower way to learn the same thing.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import reconciliation_game.corpus as corpus
import reconciliation_game.game as game

POLICY_FILE = HERE / "policy.json"


def load_policy() -> game.Policy:
    if not POLICY_FILE.exists():
        p = game.PRESETS["brief"]()
        POLICY_FILE.write_text(json.dumps(p.to_dict(), indent=2) + "\n")
        print(f"Created {POLICY_FILE.name} with 'The brief'. Edit it and run again.\n")
        return p
    return game.Policy.from_dict(json.loads(POLICY_FILE.read_text()))


def bar(label: str) -> None:
    print("\n" + label)
    print("-" * 74)


# Not one word of the copy below changes because of these two. They only
# decide where an 80-column terminal breaks a line — never what it says.
# Continuation lines line up under the TEXT, not under a label, because a
# wrapped line that starts at column 0 is barely better than no wrapping.
def wrap(text: str, indent: str = "  ", width: int = 80) -> str:
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent)


def wrap_after(prefix: str, text: str, width: int = 80) -> None:
    lines = textwrap.wrap(text, width=max(width - len(prefix), 20)) or [""]
    pad = " " * len(prefix)
    print(prefix + lines[0])
    for line in lines[1:]:
        print(pad + line)


def scoreboard(policy: game.Policy, failure_rate: float = 0.0) -> dict:
    out = game.play(policy, failure_rate=failure_rate)
    bar(f"{'Package':10} {'Score':>7} {'Wrong':>7} {'Flags':>7}  Why it is hard")
    for r in out["rows"]:
        hint = corpus.HINTS[r["package_id"]].split(".")[0]
        print(f"{r['package_id']:10} {r['score']:7} {r['wrong_accepts']:7} "
              f"{r['flags']:7}  {hint[:44]}")
    t = out["total"]
    print("-" * 74)
    print(f"{'TOTAL':10} {t['score']:7} {t['wrong_accepts']:7} {t['flags']:7}")

    if t["wrong_accepts"]:
        msg = (f"{t['wrong_accepts']} wrong values accepted. Each one costs "
               f"{abs(game.POINTS['wrong_accept'])} — more than seventy flags.")
        print("\n" + wrap(msg))
    else:
        print("\n" + wrap("Zero wrong accepts. Now see how many flags you can give back."))
    if policy.keep_identity_evidence:
        msg = (f"You are keeping identity evidence on all eight packages: "
               f"{8 * game.POINTS['evidence_retained']}. It is the single most "
               f"expensive setting on the board.")
        print(wrap(msg))
    return out


def show_package(pid: str, policy: game.Policy) -> None:
    pkg = corpus.get(pid)
    res = game.apply_policy(pkg, policy)
    sc = game.score_package(res, pkg["truth"], policy)

    bar(f"{pid} — {pkg['note']}")
    print(wrap(corpus.HINTS[pid], indent="") + "\n")
    print(f"{'Field':18} {'Accepted':22} {'Truth':22} {'Outcome':12} {'Pts':>5}")
    for d in sc["detail"]:
        print(f"{d['field']:18} {str(d['got'])[:21]:22} {str(d['want'])[:21]:22} "
              f"{d['outcome']:12} {d['points']:5}")
    print(f"{'':18} {'':22} {'':22} {'TOTAL':12} {sc['score']:5}")

    if res["conflicts"]:
        bar("Conflicts")
        for c in res["conflicts"]:
            print(f"  {c['field']}")
            for v in c["values"]:
                print(f"      {v['source']:16} {v['value']}  (conf {v['confidence']})")
    if res["flags"]:
        bar("What the checks said")
        for f in res["flags"]:
            where = f["field"] or "whole package"
            wrap_after(f"  [{f['check']}] {where}: ", f["why"])
    v = res["identity_verdict"]
    bar("Identity")
    if v is None:
        print("  no identity document — the verdict could not be computed at all")
    else:
        print(f"  name {v['name_matches']}  dob {v['dob_matches']}  "
              f"valid at incident {v['valid_at_incident']}  -> passed={v['passed']}")
        for n in v["notes"]:
            print(wrap(n, indent="    "))
    if res["retained_evidence"]:
        print("\n" + wrap(f"RETAINED: {res['retained_evidence']}"))
        msg = (f"That is {game.POINTS['evidence_retained']}, and it is data the "
               f"verdict above did not need.")
        print(wrap(msg))


def compare() -> None:
    bar(f"{'Policy':42} {'Score':>7} {'Wrong':>7} {'Flags':>7}")
    for name, make in game.PRESETS.items():
        t = game.play(make())["total"]
        print(f"{game.PRESET_LABELS[name][:41]:42} {t['score']:7} "
              f"{t['wrong_accepts']:7} {t['flags']:7}")
    print("\n" + wrap("Every one of those numbers was produced by the same engine "
                      "you are playing against."))


def resilience(policy: game.Policy) -> None:
    bar(f"{'Failure rate':14} {'Score':>7} {'Wrong':>7} {'Flags':>7}")
    for rate in (0.0, 0.1, 0.2, 0.3):
        t = game.play(policy, failure_rate=rate)["total"]
        print(f"{rate:>13.0%} {t['score']:7} {t['wrong_accepts']:7} {t['flags']:7}")
    print("\n  Losing a document does not just lose data. It loses the CHECK")
    print("  that document was there to perform. One value cannot disagree")
    print("  with anything.")
    if not policy.checks.get("completeness_gate"):
        print("\n  completeness_gate is off. Turn it on and run this again.")


def hints() -> None:
    for pid in corpus.all_ids():
        bar(pid)
        print(wrap(corpus.HINTS[pid]))


def watch() -> None:
    print("Watching policy.json. Ctrl-C to stop.\n")
    last = None
    try:
        while True:
            stamp = POLICY_FILE.stat().st_mtime if POLICY_FILE.exists() else None
            if stamp != last:
                last = stamp
                print("\033[2J\033[H", end="")
                try:
                    scoreboard(load_policy())
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"policy.json is not valid yet: {e}")
            time.sleep(0.4)
    except KeyboardInterrupt:
        print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--pkg")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--hint", action="store_true")
    ap.add_argument("--resilience", action="store_true")
    ap.add_argument("--preset", choices=sorted(game.PRESETS))
    a = ap.parse_args()

    if a.compare:
        compare(); return 0
    if a.hint:
        hints(); return 0

    policy = game.PRESETS[a.preset]() if a.preset else load_policy()

    if a.watch:
        watch(); return 0
    if a.pkg:
        show_package(a.pkg.upper(), policy); return 0
    if a.resilience:
        resilience(policy); return 0

    scoreboard(policy)
    return 0


if __name__ == "__main__":
    sys.exit(main())
