"""
app.py — The Reconciliation Game, as a board.

    pip install streamlit
    streamlit run app.py

There is no credential panel and there is nothing to connect to. If somebody
has already run the lab against the live service:

    python3 run_lab.py --provider azure

then out/azure/unified/*.json is on disk and the "Mock vs live" tab appears by
itself. Nothing to paste, nothing cached, no key in a hosted app, and no
32-document billed call behind a button in a room.

NOTE ON PYTHON VERSIONS: this file needs Python 3.9+ (streamlit>=1.30 does
not install on 3.7). The engine, play.py and the self-test run on 3.7+; see
requirements.txt.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import reconciliation_game.corpus as corpus
import reconciliation_game.game as game
from reconciliation_game.corpus import FIELDS

AZURE_DIR = HERE.parent / "out" / "azure" / "unified"

st.set_page_config(page_title="The Reconciliation Game", page_icon="🧩",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  .block-container {padding-top: 2rem; padding-bottom: 2rem;}
  .bigscore {font-size: 3.4rem; font-weight: 700; line-height: 1;}
  .sub {color: #857DA0; font-size: 0.85rem;}
  .pill {display:inline-block;padding:2px 10px;border-radius:12px;
         font-size:0.75rem;font-weight:600;margin-right:6px;}
  .ok {background:#E2F3EC;color:#10503A;}
  .bad {background:#FBE4E8;color:#78122A;}
  .flag {background:#FFF4E5;color:#7A2E00;}
</style>
""", unsafe_allow_html=True)


def init():
    if "policy" not in st.session_state:
        st.session_state.policy = game.PRESETS["brief"]()


init()


def apply_preset(name: str):
    st.session_state.policy = game.PRESETS[name]()


with st.sidebar:
    st.markdown("### Your policy")

    st.caption("Presets")
    for name in ("brief", "lab", "trust_evidence", "flag_everything"):
        st.button(game.PRESET_LABELS[name].split(" — ")[0],
                  key=f"preset_{name}", use_container_width=True,
                  on_click=apply_preset, args=(name,))

    p = st.session_state.policy

    st.divider()
    st.caption("Knobs")
    p.tolerance = st.slider(
        "Numeric tolerance", 0.0, 0.25, float(p.tolerance), 0.005,
        help="How close two numbers must be to count as the same number. "
             "Never applies to an identifier.")

    p.identifiers = set(st.multiselect(
        "Compared exactly (identifiers)", FIELDS, sorted(p.identifiers),
        help="An account number is not a number in any sense that matters. "
             "It is a name made of digits."))

    p.keep_identity_evidence = st.checkbox(
        "Keep identity evidence with the record",
        value=p.keep_identity_evidence,
        help="Attach the licence number and expiry so a reviewer can "
             "re-check it later.")

    st.divider()
    st.caption("When documents disagree, who wins")
    for f in FIELDS:
        p.strategy[f] = st.radio(
            f, game.STRATEGIES, index=game.STRATEGIES.index(p.strategy[f]),
            horizontal=True, key=f"strat_{f}", label_visibility="visible")

    st.divider()
    st.caption("Cross-document checks")
    for c, desc in game.CHECKS.items():
        p.checks[c] = st.checkbox(c, value=p.checks[c], help=desc, key=f"chk_{c}")

    st.divider()
    failure_rate = st.select_slider(
        "Document failure rate", [0.0, 0.1, 0.2, 0.3], value=0.0,
        format_func=lambda v: f"{v:.0%}",
        help="One document in N never arrives. Watch what happens to the "
             "checks that needed it.")

policy = st.session_state.policy
out = game.play(policy, failure_rate=failure_rate)
tot = out["total"]

st.markdown("## 🧩 The Reconciliation Game")
st.caption("Eight case packages, up to five documents each, one unified "
           "record — and the question of what to do when four documents "
           "disagree with each other.")

c = st.columns(5)
tone = "#1B7F5A" if tot["wrong_accepts"] == 0 else "#C0223B"
c[0].markdown(f"<div class='bigscore' style='color:{tone}'>{tot['score']}</div>"
              f"<div class='sub'>score</div>", unsafe_allow_html=True)
c[1].metric("Wrong accepted", tot["wrong_accepts"])
c[2].metric("Correct accepted", tot["correct"])
c[3].metric("Sent to a human", tot["flags"])
c[4].metric("Evidence retained",
            "yes" if policy.keep_identity_evidence else "no")

if tot["wrong_accepts"] == 0:
    st.success("Zero wrong accepts. Now see how many flags you can give back.")
else:
    st.warning(f"{tot['wrong_accepts']} wrong values accepted. Each one costs "
               f"{abs(game.POINTS['wrong_accept'])} — more than seventy flags.")

st.divider()

names = ["Per package", "Field detail", "How scoring works",
         "Policy comparison", "The packages", "Resilience"]
azure_files = sorted(AZURE_DIR.glob("*.json")) if AZURE_DIR.is_dir() else []
if azure_files:
    names.append("Mock vs live")
tabs = st.tabs(names)

with tabs[0]:
    cols = st.columns(4)
    for i, r in enumerate(out["rows"]):
        with cols[i % 4]:
            tone = "#1B7F5A" if r["wrong_accepts"] == 0 else "#C0223B"
            st.markdown(f"**{r['package_id']}**")
            st.markdown(f"<span style='color:{tone};font-size:1.6rem;"
                        f"font-weight:700'>{r['score']}</span>",
                        unsafe_allow_html=True)
            bits = []
            if r["wrong_accepts"]:
                bits.append(f"<span class='pill bad'>{r['wrong_accepts']} wrong</span>")
            if r["flags"]:
                bits.append(f"<span class='pill flag'>{r['flags']} flagged</span>")
            if not bits:
                bits.append("<span class='pill ok'>clean</span>")
            st.markdown("".join(bits), unsafe_allow_html=True)
            st.caption(corpus.HINTS[r["package_id"]][:110] + "…")
            for f in r["result"]["flags"]:
                st.caption(f"↳ **{f['check']}** — {f['why']}")

with tabs[1]:
    pid = st.selectbox("Package", corpus.all_ids())
    row = next(r for r in out["rows"] if r["package_id"] == pid)
    st.info(corpus.HINTS[pid])
    st.dataframe(
        [{"field": d["field"], "accepted": d["got"], "truth": d["want"],
          "source": row["result"]["provenance"].get(d["field"], {}).get("source"),
          "agreement": row["result"]["provenance"].get(d["field"], {}).get("agreement"),
          "outcome": d["outcome"], "points": d["points"]}
         for d in row["detail"]],
        use_container_width=True, hide_index=True)
    v = row["result"]["identity_verdict"]
    if v is None:
        st.warning("No identity document — the verdict could not be computed "
                   "at all. That is a third state, and it is not the same as "
                   "a verdict that failed.")
    else:
        st.write(f"**Identity verdict** — name `{v['name_matches']}`, "
                 f"dob `{v['dob_matches']}`, valid at incident "
                 f"`{v['valid_at_incident']}` → passed `{v['passed']}`")
        for n in v["notes"]:
            st.caption(n)
    if row["result"]["retained_evidence"]:
        st.error(f"Retained identity evidence: "
                 f"`{row['result']['retained_evidence']}` — "
                 f"{game.POINTS['evidence_retained']}. The verdict above did "
                 f"not need any of it.")

with tabs[2]:
    st.dataframe([{"outcome": k, "points": v} for k, v in game.POINTS.items()],
                 use_container_width=True, hide_index=True)
    st.markdown(
        "The asymmetry is the whole design. **One wrong acceptance costs more "
        "than seventy flags** — because a flag costs a handler half a minute "
        "and somebody knows it happened, whereas a wrongly accepted account "
        "number sends the payment to a stranger and nobody finds out until "
        "they complain.\n\n"
        "`-200` is not *the verdict was computed wrongly*. `verify_identity()` "
        "gets the verdict right on all eight packages with no checks switched "
        "on at all. It is the cost of **not acting on it**.")

with tabs[3]:
    rows = []
    for name, make in game.PRESETS.items():
        t = game.play(make())["total"]
        rows.append({"policy": game.PRESET_LABELS[name], "score": t["score"],
                     "wrong": t["wrong_accepts"], "flags": t["flags"]})
    rows.append({"policy": "— your policy —", "score": tot["score"],
                 "wrong": tot["wrong_accepts"], "flags": tot["flags"]})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption("Every number here was produced by the engine you are playing "
               "against, not typed into a slide.")

with tabs[4]:
    for pid in corpus.all_ids():
        st.markdown(f"**{pid}** — {corpus.get(pid)['note']}")
        st.caption(corpus.HINTS[pid])

with tabs[5]:
    st.markdown("#### Your policy, as documents start going missing")
    rows = []
    for rate in (0.0, 0.1, 0.2, 0.3):
        t = game.play(policy, failure_rate=rate)["total"]
        rows.append({"failure rate": f"{rate:.0%}", "score": t["score"],
                     "wrong": t["wrong_accepts"], "flags": t["flags"]})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.markdown(
        "> Losing a document does not just lose data. It loses the **check** "
        "that document was there to perform. One value cannot disagree with "
        "anything.")
    if not policy.checks.get("completeness_gate"):
        st.warning("`completeness_gate` is off. Switch it on and read this "
                   "table again.")

# ==========================================================================
# Mock vs live — CORRECTED per plan Ruling F-11.
#
# The brief's version compared the PLAYER'S current policy against the fixed
# recorded run and marked every difference "VERDICT". That mixes two axes: a
# difference can come from the STRATEGY (trust_form vs reconcile vs
# trust_evidence) or from the SERVICE (Query Fields vs real Azure Document
# Intelligence). Under the default "brief" preset the player runs trust_form
# while every recorded azure run used "reconcile" — so nearly every row would
# light up, and every one of those lit rows would be a strategy difference
# wearing a service-difference label.
#
# The honest comparison holds the strategy fixed: read which strategy
# actually produced each azure record, run that SAME strategy against the
# mock corpus, and mark VERDICT only where the two diverge. That isolates the
# one variable the tab claims to be testing. The player's own policy is shown
# alongside for context, but never drives the VERDICT column.
# ==========================================================================
def _policy_for_strategy(name: str):
    """Map a recorded pipeline strategy to the preset that reproduces it.

    Returns (label, Policy) for a strategy this board knows how to
    reproduce, or (None, None) for one it does not — in which case there is
    no honest like-for-like comparison to make, and the tab must say so
    rather than guess.
    """
    if name == "reconcile":
        return game.PRESET_LABELS["lab"], game.PRESETS["lab"]()
    if name == "trust_evidence":
        return game.PRESET_LABELS["trust_evidence"], game.PRESETS["trust_evidence"]()
    if name == "trust_form":
        return ("trust_form — every field trusts the case form, no checks",
                game.Policy(strategy={f: "trust_form" for f in FIELDS},
                           checks={c: False for c in game.CHECKS}))
    return None, None


if azure_files:
    with tabs[6]:
        st.caption(f"Read from `{AZURE_DIR}` — written by "
                   "`run_lab.py --provider azure`. Nothing was called from here.")

        live_records = [json.loads(f.read_text()) for f in azure_files]
        strategies_seen = sorted({r.get("strategy") for r in live_records})

        matched_policy = None
        if len(strategies_seen) > 1:
            st.error(
                "The recorded packages do not agree with each other about "
                "which strategy produced them: "
                f"{', '.join(repr(s) for s in strategies_seen)}. Refusing to "
                "silently pick one — this tab will not mark any `VERDICT` "
                "until `out/azure/unified` is regenerated with one strategy "
                "throughout.")
        else:
            recorded_strategy = strategies_seen[0] if strategies_seen else None
            label, matched_policy = _policy_for_strategy(recorded_strategy)
            if matched_policy is None:
                st.warning(
                    f"Every record on disk was produced with strategy "
                    f"`{recorded_strategy}`, which this board has no preset "
                    "for. Showing the raw values below with no `VERDICT` "
                    "marking, because there is no honest like-for-like "
                    "comparison to make against an unrecognised strategy.")
            else:
                st.info(
                    f"Every `out/azure/unified/*.json` record on disk was "
                    f"produced with strategy **`{recorded_strategy}`**. Both "
                    f"the *mock* and *live* columns below run **that same "
                    f"strategy** — {label} — so the only thing left free to "
                    "differ is which service supplied the field values: "
                    "Query Fields, or the real, billed Azure Document "
                    "Intelligence run. A `VERDICT` row is a case where the "
                    "extraction service changed the answer, not a case "
                    "where your own policy would have decided differently. "
                    "Your policy's value is shown alongside for context and "
                    "does not drive the `VERDICT` marking.")

        mock_rows_by_pid = {}
        if matched_policy is not None:
            mock_rows_by_pid = {r["package_id"]: r
                                for r in game.play(matched_policy)["rows"]}

        table = []
        verdict_count = 0
        for live in live_records:
            pid = live.get("package_id")
            live_unified = live.get("unified", {})
            mock_row = mock_rows_by_pid.get(pid)
            player_row = next((r for r in out["rows"] if r["package_id"] == pid), None)
            for fld in FIELDS:
                live_val = live_unified.get(fld)
                mock_val = mock_row["result"]["unified"].get(fld) if mock_row else None
                player_val = (player_row["result"]["unified"].get(fld)
                              if player_row else None)
                verdict = ""
                if matched_policy is not None and mock_val != live_val:
                    verdict = "VERDICT"
                    verdict_count += 1
                table.append({"package": pid, "field": fld,
                             "mock (same strategy)": mock_val,
                             "live (azure)": live_val,
                             "your policy (context only)": player_val,
                             "": verdict})
        st.dataframe(table, use_container_width=True, hide_index=True)

        if matched_policy is not None:
            if verdict_count:
                st.markdown(
                    f"**{verdict_count}** row(s) marked `VERDICT` — fields "
                    "where the SAME strategy reached a different answer "
                    "depending on which service extracted the documents. "
                    "That is a real service difference, not a strategy "
                    "difference.")
            else:
                st.markdown(
                    "No row is marked `VERDICT`. On this corpus, the "
                    "reconciliation logic reached the same unified value "
                    "from Query Fields and from the real Azure Document "
                    "Intelligence run, field for field. The `your policy` "
                    "column may still disagree with both — that is your "
                    "policy's own choice of strategy and checks showing "
                    "through, not a service difference, and it does not "
                    "earn a `VERDICT`.")
