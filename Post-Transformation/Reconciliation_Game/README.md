# The Reconciliation Game

**Birlasoft FORGE FDE Academy · DecisionStream AI · Sprint 1 Day 15 · Confidential — Trainer & Learner Use**

Eight case packages, up to five documents each, six fields per package. The
four documents disagree with each other. You decide which value goes into the
record, which value goes to a human, and what the record is allowed to keep.

A flag costs half a minute of handler time. A wrongly accepted account number
sends the payment to a stranger.

This is the companion to the Day 15 multi-document lab in the folder above. The
lab shows you what reconciliation does. The game makes you pay for choosing it
badly.

> Every score printed in this file was produced by the engine in
> `reconciliation_game/game.py` — the same engine the room plays against.
> Nothing here is asserted. The commands that produced each number are named
> beside it.

---

## 1 · Two ways to play

### The terminal — nothing to install

```bash
python3 play.py --watch
```

Standard library only. No `pip`, no network, no server. It runs on **Python
3.7 and newer** — verified on 3.7.2, where `reconciliation_game/selftest_game.py`
reports **218/218**.

**This is the version to default to in a room.** It is the one that will not
cost you fifteen minutes of the session, and it is the reason it exists.

Then **split your VS Code window**: `policy.json` on the left, the watching
terminal on the right. Change a number, save, and the score moves before you
have looked back up. `Ctrl+Shift+B` runs the watcher — the task is already in
`.vscode/tasks.json`.

Other commands:

```bash
python3 play.py --compare              # every preset, scored
python3 play.py --pkg PKG-008          # one package, field by field
python3 play.py --hint                 # what each package is testing
python3 play.py --resilience           # scores at 0 / 10 / 20 / 30% document loss
python3 play.py --preset all_checks    # score a named preset
```

### The Streamlit board — nicer, needs one install and a newer Python

```bash
pip install streamlit
streamlit run app.py
```

Six tabs — seven when a live run is on disk, see §8 — plus sliders and
live tables. It needs **Python 3.9 or newer**:
`streamlit>=1.30` does not install on 3.7, and the board uses `st.tabs`,
`hide_index` and `use_container_width`, none of which exist in the Streamlit
that would install there.

**If `streamlit run app.py` fails, check `python3 --version` before you check
anything else.** Run it with `python3.9` or `python3.11` rather than with
whatever `python3` happens to be. The engine, `play.py` and the self-test do
not care; only the board does.

There is **no credential panel and no Azure button**. If a trainer has already
run `python3 run_lab.py --provider azure` in the lab folder, the unified
records are on disk and the *Mock vs live* tab appears by itself. If not, the
tab is absent and everything else works. Nothing in this folder can start a
billed call.

---

## 2 · How scoring works

| Outcome | Points | Why |
|---|---|---|
| A correct value accepted into the record | **+10** | The work you saved |
| A **wrong** value accepted | **−150** | The case you broke |
| A value refused and sent to a human | **−2** | Thirty seconds of handler time |
| A required field absent and not flagged | **−20** | A silent gap |
| A value accepted that **requires evidence** and came from the form alone | **−60** | Declared, not evidenced |
| A record accepted although the **identity verdict did not pass** | **−200** | You computed the verdict and ignored it |
| An identity verdict **impossible** and not flagged | **−40** | No document, no check, no note |
| **Identity evidence retained**, per package | **−300** | See §7 |

The asymmetry is the whole design. **One wrong acceptance costs more than
seventy flags.** A flag costs a handler half a minute and somebody knows it
happened. A wrongly accepted account number sends the payment to a stranger and
nobody finds out until they complain.

Two of those constants need their wording defended, because getting either one
backwards would have made a check worthless.

**−200 is for ignoring the verdict, not for computing it wrongly.**
`verify_identity()` in the lab already returns the correct verdict for all
eight packages with no checks switched on at all. What the lab does not do is
**act** on it — a failed verdict never stops the record being assembled. So the
penalty attaches to accepting a record whose verdict did not pass, which is
exactly what `identity_match` and `identity_validity` exist to prevent. Scored
the other way round, both checks would be worth zero.

**−60 for an unevidenced accept, not −150.** PKG-006's income is *correct* —
47,000 really is the number. Charging a wrong-accept penalty for a right answer
would be dishonest scoring. The defect is that the record cannot tell
`declared` from `evidenced`, which is worth real money and is not worth a
broken case. Without this line, `evidence_required` could only ever cost flags,
and would be a check nobody rationally switches on.

**Scored surface:** 8 packages × 6 fields = 48 field decisions, plus 8 identity
verdicts, plus 8 scope decisions.

---

## 3 · What players discover

Start with **The brief** — trust the applicant everywhere, tolerance 0.02, no
checks, keep the identity evidence. That is what the curriculum literally
specifies. It scores **−3350**.

Then people tune. Tuning does not save them.

```bash
python3 play.py --compare
python3 reconciliation_game/search.py --trials 4000
```

| Strategy | Score | Wrong accepts | Flags |
|---|---|---|---|
| The brief — trust the applicant, no checks, keep the evidence | −3350 | 6 | 0 |
| Trust the paperwork — precedence decides, no checks | −3030 | 4 | 0 |
| Flag everything — reconcile, zero tolerance | −2450 | 0 | 5 |
| The lab — reconcile everywhere, no checks | −14 | 0 | 2 |
| **Best tuning found by a 4,000-trial search, no checks** | **−2** | **0** | 1 |
| **All checks on — the brief's knobs, untouched** | **204** | **0** | 23 |
| All checks on, plus tight knobs | 192 | 0 | 24 |

Everything except the search row comes from `--compare`. The search row comes
from `search.py`, which also reprints the all-checks-on figure of 204 for
comparison at the bottom of its own output.

### Finding one — the ceiling is a lower bound, and it is short of 204

A random search over knob-space with **every check switched off** gets no
further than **−2** in 4,000 trials. Turning every check on and touching no knob at all
scores **204**.

Say this out loud when you quote it: **a random search finds the best policy it
happened to try, never provably the best there is.** −2 is a *lower bound* on
what tuning can reach, not a proof of a ceiling. A learner who beats it has not
broken the game — they have found a policy the search missed, and the finding
still holds as long as the checks beat them.

What can be said is that the number is stable under re-seeding. Four
independent searches:

```bash
for s in 3 11 29 101; do python3 reconciliation_game/search.py --trials 4000 --seed $s; done
```

| Seed | Best score found | Wrong accepts |
|---|---|---|
| 3 | −2 | 0 |
| 11 | −2 | 0 |
| 29 | −2 | 0 |
| 101 | −2 | 0 |

Four seeds, 16,000 trials, the same answer. That is evidence the search is not
just unlucky. It is still not a proof, and this file will not call it one.

### Finding two — the 206-point gap is not made of wrong accepts

Unlike Day 14, tuning here *can* reach zero wrong accepts. The best policy the
search found has none. So where do the 206 points go?

| Best tuned policy, no checks | Points |
|---|---|
| 46 fields accepted correctly | +460 |
| 1 field refused | −2 |
| 1 income accepted from the form alone, unevidenced | −60 |
| 2 records accepted although the identity verdict did not pass | −400 |
| **Total** | **−2** |

Two packages — PKG-002 and PKG-003 — have an identity verdict that fails, and
the tuned policy assembles their records anyway. No arrangement of tolerance,
identifiers and per-field strategy can see that, because the verdict is not a
field. Only a check can act on it.

> Tuning moves **who looks at** a value.
> Validation changes **whether the value is right**.

### Finding three — tightening on top of working validation buys nothing

*All checks on, plus tight knobs* scores **192** against **204** for all checks
on alone, and buys one extra flag (24 against 23) while preventing nothing —
both are already at zero wrong accepts. This is the same result the Day 14 game
produces, reached by the room rather than delivered to it.

### Finding four — refusing everything is not the answer either

*Flag everything* scores **−2450**, and it is tempting to read that as proof
that flagging is expensive. **It is not, and a learner who checks will catch
you.** Almost all of that number is the identity-evidence knob, which the preset
inherits from the brief: 8 packages × −300 = −2400. Switch the knob off and the
same preset scores **−50**.

So the honest comparison is:

| Policy | Score | Wrong accepts | Flags |
|---|---|---|---|
| Flag everything, identity evidence off | −50 | 0 | 5 |
| All checks on | **204** | 0 | 23 |

Refusing everything does reach zero wrong accepts, and it scores −50 against
204. The gap is 254 points — and it is **not** the price of refusing. Reading it
that way gets the lesson backwards.

Start by noticing that refusing everything is not even especially cautious with
values. Zero tolerance only surfaces a conflict where the documents actually
differ, so it accepts **42** of the 48 fields and refuses 5. All checks on
accepts **25** and refuses 23. Validating accepts **seventeen fewer** fields
than the blanket refusal does.

| | Flag everything, evidence off | All checks on |
|---|---|---|
| Fields accepted correctly | 42 (+420) | 25 (+250) |
| Fields refused | 5 (−10) | 23 (−46) |
| Income accepted unevidenced | 1 (−60) | 0 |
| Records accepted on a **failed identity verdict** | 2 (**−400**) | 0 |
| **Total** | **−50** | **204** |

Read down the two columns and the 254 points come apart cleanly. Validating
gives up 170 points of accepted value and pays 36 points of extra flags, and it
buys back 60 for the unevidenced income and **400 for the two failed identity
verdicts it stops being ignored**.

**Refusing cost 10 points. The identity verdicts cost 400.**

So the finding is not that caution is expensive. It is that a blanket refusal
is caution about **values**, and the two packages it loses on have nothing
wrong with their values at all: PKG-002's name does not match the licence, and
PKG-003's licence had expired before the incident. A policy that refuses every
disputed number still assembles both of those records and still ignores both
verdicts.

> No amount of caution about what a number says substitutes for checking **who
> this is.**

*(Verify with:*

```bash
python3 -c "
import sys, collections; sys.path.insert(0, '.')
import reconciliation_game.game as g
def bd(p, name):
    out = g.play(p); c = collections.Counter(); pts = collections.Counter()
    for row in out['rows']:
        for d in row['detail']:
            c[d['outcome']] += 1; pts[d['outcome']] += d['points']
    print(name, out['total']['score'], dict(c), dict(pts),
          'package-level:', out['total']['score'] - sum(pts.values()))
fe = g.PRESETS['flag_everything'](); fe.keep_identity_evidence = False
bd(fe, 'flag_everything, evidence off:')
bd(g.PRESETS['all_checks'](), 'all_checks:')
"
```

*)*

---

## 4 · The eight packages

```bash
python3 play.py --hint
```

| Package | What makes it hard | The check that addresses it |
|---|---|---|
| PKG-001 | Clean — everything agrees. The control. | none, and none should |
| PKG-002 | The name on the licence is not the name on the form | `identity_match`, `cross_doc_name` |
| PKG-003 | Identity document expired before the incident | `identity_validity` |
| PKG-004 | Declared income is 42% above the payslip | `evidence_required` |
| **PKG-005** | **Account number differs by one digit** | the `identifiers` knob, not a check — see §5 |
| PKG-006 | Payslip missing — income is right and unevidenced | `evidence_required`, `completeness_gate` |
| PKG-007 | Two payslips, two months, two very different amounts | `period_coherence` |
| **PKG-008** | **Bank statement belongs to a different person** | `cross_doc_name` only |

**That last column is a judgement, not a measurement, and it is the only one in
this file.** It names the check written to address each package's defect. It is
not the list of checks that flag the package, which is wider — `evidence_required`
also flags PKG-005, PKG-007 and PKG-008, because all three source a field from
the form alone as well as having their own problem. Measure that yourself:

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
import reconciliation_game.game as g
for c in g.CHECKS:
    p = g.PRESETS['brief'](); p.checks[c] = True
    print(c, '->', [r['package_id'] for r in g.play(p)['rows']
                    if any(f.get('check') == c for f in r['result'].get('flags', []))])
"
```

The numbers in §5 are measurements: each is the whole-board score delta from
switching that one check on against the brief preset.

### PKG-005 — the one that nearly got through

The account number on the form is `20558193`. On the bank statement it is
`20558198`. A numeric comparison with the brief's 2% tolerance calls those
equal — they differ by 5 out of twenty million.

They are not equal. They are different accounts and the payment goes somewhere
else.

An account number is not a number in any sense that matters. It is a name made
of digits. **Tolerance applies to quantities, never to identifiers** — which is
what the `identifiers` knob is for, and what `tolerance_guard` exists to
enforce when a player empties it. See §5 for what happens when they do, because
the answer on this corpus is not the one you expect.

### PKG-008 — the one that should worry you

**Its identity verdict passes.**

That is the single most important property in the corpus. The identity document
matches its own form perfectly: the name is right, the date of birth is right,
the document had not expired. Identity verification runs, succeeds, and reports
success. Every field on the bank statement is high confidence and internally
consistent — the sort code is valid, the period is right. It is simply the
wrong person's statement, attached to the package by mistake.

Nothing about any single **document** is wrong. What is wrong is the
relationship between one document and the other three, and no per-document
check can see a relationship.

Only `cross_doc_name` gets PKG-008 to zero wrong accepts — the check that
asserts the same person must appear on **every** document that carries a name.
Switch it off with every other check left on and the package scores −100 with
one wrong accept: the stranger's name goes into the record, under a clean
identity verdict. `evidence_required` still catches the account number, which
is why it is one wrong accept and not two — turn both off and PKG-008 scores
−260 with two.

Then ask the room the harder question: would that check catch a subtler
version, where the name on the statement is *similar* rather than different?

---

## 5 · The seven checks

Worth alone is measured by switching one check on against the brief preset and
taking the difference from its −3350:

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
import reconciliation_game.game as g
base = g.play(g.PRESETS['brief']())['total']['score']
for c in g.CHECKS:
    p = g.PRESETS['brief']()
    p.checks[c] = True
    print(f'{c:20} {g.play(p)[\"total\"][\"score\"] - base:+6}')
"
```

| Check | What it does | Worth alone |
|---|---|---|
| `identity_match` | Name and date of birth on the identity document must match the form | **+300** |
| `identity_validity` | The identity document must not have expired before the incident | +128 |
| `cross_doc_name` | The same person must appear on every document that carries a name | **+572** |
| `evidence_required` | Income and account number may not come from the applicant's own form alone | **+674** |
| `period_coherence` | Two payslips covering different periods cannot both feed one income figure | +160 |
| `completeness_gate` | Every expected document must have arrived — a missing document is a missing check | **−2** |
| `tolerance_guard` | Numeric tolerance must never be applied to an identifier | **+0** |

Five of those pay for themselves the moment they are switched on. The other two
are the interesting ones, and both are worth letting somebody discover and
complain about.

### `completeness_gate` is worth −2 on a healthy run

It costs one flag and prevents nothing, because on a healthy run every document
arrives. Switching it off actually *improves* the all-checks score from **204**
to **264**, with five fewer flags.

Now run both at a 20% document-loss rate:

| `completeness_gate` | 0% failures | 20% failures |
|---|---|---|
| **on** | 204, 0 wrong, 23 flags | −48, **0 wrong**, 44 flags |
| off | 264, 0 wrong, 18 flags | −404, **3 wrong**, 7 flags |

Sixty points cheaper on a good day, three wrong accepts on a bad one. That is
the shape of every availability control anybody has ever had to justify in a
design review, and the game makes the argument arithmetically instead of
rhetorically.

### `tolerance_guard` is worth exactly nothing, and it is still right

It is worth +0 against every preset, because `account_number` is already in the
`identifiers` set in all of them — the guard has nothing to add. It only does
anything at all once a player empties that set.

And when they do, on this corpus, it makes the score **worse**. Sweep a large
random sample of policies with the guard forced off and then on, and the result
is one-sided: it **never improves a score**, it **never removes a wrong
accept**, and it sometimes adds one.

```bash
python3 -c "
import sys, copy, random; sys.path.insert(0, '.')
import reconciliation_game.game as g
from reconciliation_game.corpus import FIELDS
rng = random.Random(5); TOL = [0.0, 0.005, 0.01, 0.02, 0.05, 0.10, 0.15, 0.25]
helped = hurt = fewer_wrong = more_wrong = 0
for _ in range(6000):
    base = g.Policy(strategy={f: rng.choice(g.STRATEGIES) for f in FIELDS},
                    tolerance=rng.choice(TOL),
                    identifiers={f for f in FIELDS if rng.random() < 0.5},
                    checks={c: rng.random() < 0.5 for c in g.CHECKS},
                    keep_identity_evidence=rng.random() < 0.5)
    off = copy.deepcopy(base); off.checks['tolerance_guard'] = False
    on  = copy.deepcopy(base); on.checks['tolerance_guard']  = True
    a = g.play(off)['total']; b = g.play(on)['total']
    helped += b['score'] > a['score'];  hurt += b['score'] < a['score']
    fewer_wrong += b['wrong_accepts'] < a['wrong_accepts']
    more_wrong  += b['wrong_accepts'] > a['wrong_accepts']
print('helped', helped, '| hurt', hurt,
      '| removed a wrong accept', fewer_wrong, '| added one', more_wrong)
"
```

The counts of *how often* depend on how you sample — change the seed or the
mix and they move. The two numbers that matter do not: **helped 0** and
**removed a wrong accept 0**, every time.

Here is why, and the reason is worth the five minutes it will cost you:

| Strategy on `account_number`, `identifiers` empty | Guard off | Guard on |
|---|---|---|
| `trust_form` | `20558198` — **correct**, +10 | `20558193` — **wrong**, −150 |
| `trust_evidence` | `20558198` — correct, +10 | `20558198` — correct, +10 |
| `reconcile` | `20558198` — **correct**, +10 | refused, −2 |

With the guard off, tolerance quietly merges the two account numbers into one
agreed value, and on this corpus that merge happens to land on `20558198` —
which is the right one. The guard refuses to merge them, surfaces a real
conflict, and hands the decision to your strategy. If your strategy is "the
applicant wins", the decision is wrong.

**The guard did not cause that. It revealed it.** Without the guard the record
was right by accident, and the accident is not reproducible — change one digit
of the corpus and it lands the other way. This is the difference between a
policy that is correct and a policy that got the right answer, and it is
visible here only because the score went down.

That is a real phenomenon rather than a bug, and it is the one to put in front
of a room that has started to believe the leaderboard is the truth.

---

## 6 · `keep_identity_evidence` — the most expensive setting on the board

In the Day 14 game, `scope_gate` was the most valuable single check at +300.
The most valuable validator in that set was not an accuracy control at all — it
was a **scope** control. That is the finding the whole Sprint 0 Day 3 decision
rests on.

It cannot be reproduced here, and the reason is that the lab already got it
right. `pipeline.stitch()` has no mapping for `document_number`, `expiry_date`
or `issuing_country` in `FIELD_SOURCES`, so those fields cannot reach a unified
record however hard you push. A scope *check* would be worth exactly zero and
would teach nothing.

So the lesson is inverted. It is not a check you can earn points by switching
on. It is a **knob that sounds like diligence**:

> **`keep_identity_evidence`** — *attach the licence number and expiry date to
> the record so a reviewer can re-check the verdict later.*

Read that sentence to a room and ask for a show of hands. It is defensible. It
is auditable. It is what a careful person builds. It is **on by default in the
brief preset**, because it is what a careful person building to that brief
would have done.

It costs **−300 per package** — 8 packages, **−2400**, the single most
expensive line anywhere in the scoring:

| Policy | Evidence on | Evidence off | Difference |
|---|---|---|---|
| The brief | −3350 | −950 | −2400 |
| Flag everything | −2450 | −50 | −2400 |
| All checks on | −2196 | **204** | −2400 |

Three things make this the best knob on the board.

**One. It is the only setting that cannot be recovered by tuning anything
else.** Every other mistake in this game has a compensating move somewhere.
This one does not: it is a flat charge per package, and no strategy, tolerance
or identifier set touches it. The 4,000-trial search found that out on its own
— the best policy it returned has `keep evidence  False`, and the search was
never told what that field means.

**Two. It punishes the clean package.** Under the brief, PKG-001 — everything
agrees, no conflict, nothing wrong with it at all — scores **−240**. Its six
correct fields earn +60 and the retention charge takes 300 straight back off.
There is no defect to find and no check to switch on. The only way to score on
PKG-001 is to stop keeping something you did not need.

**Three. It turns the lab's own rule into something the room loses points to.**
The lab's README §2 says it in one line:

> You process the identity document. You keep the verdict. You discard the
> evidence.

That is a slide. Slides get nodded at. This is a −2400 hole in a scoreboard
that somebody has spent twenty minutes trying to climb out of by tuning, and
when they finally find the checkbox they do not need to be told again what it
meant. **Nobody argues with a scoreboard.**

The knob is also the reason §3's Finding four matters. *Flag everything* looks
like it proves that refusing costs you −2450. It does not. −2400 of that is
this knob, and the flags themselves cost 5 × −2 = −10. Quote the −2450 as
evidence against flagging and the first person to switch the knob off will
correct you in front of the room.

---

## 7 · Resilience — what happens when a document does not arrive

Day 14 had no equivalent of this. The lab's Step 3 does:

```bash
python3 run_lab.py --strategy reconcile --failures 0.2
```

The game scores your policy at four loss rates at once, reusing the lab's
seeded injection so every learner sees the same table:

```bash
python3 play.py --preset all_checks --resilience
python3 play.py --preset brief --resilience
```

**All checks on:**

| Failure rate | Score | Wrong accepts | Flags |
|---|---|---|---|
| 0% | 204 | 0 | 23 |
| 10% | −148 | 1 | 39 |
| 20% | −48 | 0 | 44 |
| 30% | −48 | 0 | 44 |

**The brief:**

| Failure rate | Score | Wrong accepts | Flags |
|---|---|---|---|
| 0% | −3350 | 6 | 0 |
| 10% | −3350 | 6 | 0 |
| 20% | −870 | 6 | 0 |
| 30% | −870 | 6 | 0 |

Two things to point at.

**A good policy degrades and a bad policy does not.** The all-checks score
falls 352 points between 0% and 10% while the brief does not move at all. That
is not the brief being robust. It is the brief already being so wrong that
losing documents cannot make it much worse — and at 20% its score *improves* to
−870, because packages that never fully arrive stop being assembled, and a
record that was never assembled cannot retain identity evidence it does not
have. **A rising score is not always good news.** Ask the room what they think
happened before you tell them.

**The 10% row is where the lesson lives.** All checks on, one wrong accept
appears. Nothing about the stitching got worse. A lost document removed the
second opinion that made a conflict visible, and one value cannot disagree with
anything.

> Losing a document does not just lose data. It loses the **check** that
> document was there to perform.

That is what `completeness_gate` is for, and §5 has the arithmetic: with it on,
zero wrong accepts at 20%; with it off, three.

The failure injection is seeded, so a given rate fails the same document type in
every package and every learner sees an identical table. That is deliberate —
the lesson is legible instead of noisy. It is not a model of how real failures
distribute, and it should not be quoted as one.

---

## 8 · Mock against the live service

If `out/azure/unified/*.json` exists in the lab folder above, the Streamlit
board grows a seventh tab. Those records come from a real, billed Azure
Document Intelligence run over the 32 rendered PDFs.

The tab holds the strategy fixed — it reads which strategy produced the
recorded run and scores the mock with that same strategy — so the only thing
left free to differ is which service supplied the field values.

On the corpus as shipped, the eight recorded records were all produced with
`reconcile`, and the comparison is 8 packages × 6 fields = **48 cells with zero
differences**.

**That is a result, not a missing feature.** It says the mock provider is a
faithful stand-in for the real service on this corpus, which is what makes the
offline game worth playing at all. It is also the lab's own headline: every
defect in this corpus lives *between* documents, so a better extraction service
cannot fix any of them and a worse one would not have caused them. Extraction
is a purchased service. Reconciliation is yours.

Do not promise a room drama on that tab. Promise them the finding.

---

## 9 · Running the session (45 minutes)

| Time | What happens |
|---|---|
| 0–5 | Everyone opens **The brief** and reads the score: **−3350**, six wrong accepts. Ask what they would fix first. |
| 5–20 | **Tune only.** Checks stay locked off. Knobs are open: tolerance, identifiers, per-field strategy. Pods compete on score. |
| 20–25 | Collect scores. Nobody is above zero. Show the search: the best policy 4,000 trials found, with every check off, scores **−2**. Let that sit. |
| 25–35 | **Checks unlocked.** All checks on with no knob touched scores **204**. The leaderboard inverts inside two minutes. |
| 35–45 | Best pod presents. Then §6, then the strategy table, then the resilience table. |

**That lock is social, not technical.** Every checkbox in the Streamlit board
and every field in `policy.json` is live from the first minute; nothing in the
code stops a pod from switching them all on during 5–20. Say so to the room,
and say why — a pod that does it reaches roughly 204 almost immediately, and
has skipped the part of the exercise that gives that number meaning. If it
happens, do not tell them off. Ask what they learned getting there.

**The 20–25 minute pause matters.** Let the room be genuinely stuck before you
unlock the checks. The frustration is what makes the second half land, and it
is the reason the tuning ceiling is measured rather than asserted — you need to
be able to tell them their twenty minutes of tuning could not be improved on by
a 4,000-trial random search, and be right.

Say it that way rather than "−2 is the best there is". §3 does not claim that
and neither should you, out loud, in front of somebody who might go and find
−1. The measured claim is strong enough on its own and it cannot be
embarrassed.

**A question worth asking at minute 22:** *"has anyone got to zero wrong
accepts, and what did it cost?"* Somebody will have found that refusing
everything does it. Their score is −2450, or −50 once they find the evidence
knob. Neither is a policy anybody would ship, and both beat most of the room,
which is the uncomfortable part.

**The question to save for minute 40:** *"which single setting cost you the
most, and would you have defended it in a design review this morning?"* The
answer is `keep_identity_evidence`, at −2400, and the honest answer to the
second half is yes.

---

## 10 · Files

```
README.md                       this file
app.py                          the Streamlit board — 7 tabs, needs Python 3.9+
play.py                         the terminal version, with --watch. stdlib only
policy.json                     the file players edit (created on first run)
requirements.txt                streamlit only
reconciliation_game/
  __init__.py
  corpus.py                     adapter: the lab's packages, extended truth, hints
  game.py                       Policy, apply_policy, scoring, presets
  search.py                     searches for the best score tuning alone reaches
  selftest_game.py              218 checks, including the pin test
design/
  2026-08-18-reconciliation-game-design.md
.vscode/tasks.json              Ctrl+Shift+B runs the watcher
```

`game.py` and `play.py` are standard library only. `app.py` is the only file in
the project that imports Streamlit, and that is deliberate: a learner on a
locked-down VM with no `pip` still gets the entire game.

The game **imports** the lab. It does not copy it and it does not modify it.
The eight packages, their truth and `verify_identity()` all come from
`multidoc_lab/`.

---

## 11 · For whoever maintains this

```bash
python3 reconciliation_game/selftest_game.py     # must print 218/218
cd .. && python3 run_lab.py --selftest           # must still print 108/108
cd .. && python3 run_lab.py                      # must still print 4 / 2 / 0
```

All three must pass before anything ships. The last two matter because the game
extended each package's `truth` dict from two scored fields to six, and the
lab's own scoring reads that same dict.

**The pin test is what stops the game and `pipeline.stitch()` drifting apart.**
The game implements its own `apply_policy()` rather than adding six parameters
to `stitch()`, because `stitch()` is the reference code learners *read* in Step
1 of the lab and six knobs would destroy the thing that makes it legible. The
cost of that choice is two implementations of overlapping logic. The pin test
is what pays it: with checks off and the lab's own settings, the game's
`unified` dict must equal `pipeline.stitch(doc_fields, "reconcile")["unified"]`
for all eight packages, with the same `source` and `agreement` on every field.

Change `stitch()` and this test fails, and the game gets corrected. Change the
game's engine and it fails, and you find out before a room does. **The lab
remains the source of truth for what reconciliation means.**

**The property test is what stops a scoring change quietly inverting the
lesson.** It asserts four orderings, not one:

1. All checks on, knobs untouched, scores higher than the best policy
   `search.py` finds with every check off — **204 against −2**.
2. That all-checks-on policy reaches **zero** wrong accepts.
3. *Flag everything* scores worse than all checks on — refusing everything is
   not the answer either.
4. All checks on plus tightened knobs scores no better than all checks on alone
   — **192 against 204**.

The game only teaches the right thing while validation strictly dominates
tuning, and that is a property of the eight constants in `POINTS`, not of the
prose in this file.

**Those constants are tuned deliberately.** If you raise `correct_accept`,
soften `wrong_accept` or reduce `evidence_retained`, you have changed the
lesson, whether or not you meant to. Re-run `play.py --compare`,
`search.py --trials 4000` and the per-check table in §5, and **update the
numbers in this README from the output** rather than adjusting them by hand.
Every figure here was pasted from a command. Keep it that way — a made-up
number in this file would discredit the one thing the game is for.

There is no second implementation of the scoring rules. Day 14 carried a
JavaScript engine inside its HTML board and needed `verify.py` to stop the two
drifting; this project ships Python only, so there is nothing to keep in sync
and no `build_html.py` to forget to run.
