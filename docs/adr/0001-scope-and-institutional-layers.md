# ADR 0001 — Scope, institutional layers, and the transparent-institution gate

- Status: **Accepted** (2026-07-12)
- Deciders: spec-governor (conflict map), integration-manager (author), reviewed independently
  by adversarial-reviewer + reality-auditor (see `docs/reviews/T01-*`).
- Supersedes (in part): `CLAUDE.md` §2 điều luật #7 (absolute prohibition of named
  institutions), `SPEC.md` §0 rows 1/9/10, `PHASES.md` Phase 4 calibration criterion,
  `REPORTS.md` (manifesto claim tier). History is preserved; superseded passages are marked
  in place with a pointer here.
- Context sources: `REVIEW.md`, `TASKS.md` (execution authority), `docs/MODEL_CHARTER.md`,
  `docs/reviews/T00-spec-governor-conflict-map.md`.

## Context

THÓC's original charter (`CLAUDE.md`, `SPEC.md`) mandated **radical emergence**: the engine may
contain only physics + 3 primitives (contract, legal entity, invention); *no named institution*
(bank/loan/company/wage/tax/government) may exist as engine code. The current working tree,
however, already ships named institutions: `ChinhQuyen` (state), tax, minimum wage, Gini-gated
riot confiscation (`engine/politics.py`, `engine/world.py`, `config/world.yaml`), commodity
`xu`, and legal entities. `REVIEW.md` and `TASKS.md` re-scope the project toward an auditable
*mechanism benchmark* for the agrarian→exchange→credit→money→fiscal path, which explicitly
*requires* transparent `credit`/`money`/`fiscal` modules — but only under strict conditions.

This is a genuine, un-ignorable specification conflict (conflict map items C1, C2, C3, C6, C12).
We resolve it deliberately rather than silently picking a side.

## Decision

### A. Preserve the invariants (non-negotiable)

The following remain hard invariants and are NOT weakened by anything below:
1. Resource conservation + FlowRegistry audit **after every tick** (CLAUDE.md #1).
2. Double-entry ledger, no negative balances; debt is a `Claim` object, never a negative number (#2).
3. LLM/policy return intent only; engine validates against a whitelist before applying (#3).
4. Determinism & replay: a single RNG tree; same seed + same transcript → same world-hash (#4).
   **Extended (§D): all behavior-affecting state must enter the world-hash/replay or carry an
   explicit versioned artifact.**
5. Mock-before-real; full event/call provenance (#5, #6).

### B. Replace the absolute institution ban with a transparent-institution gate

`CLAUDE.md` #7's *absolute* prohibition is **superseded** by the gate in
`MODEL_CHARTER.md` §5. A named institution module may live in the engine **iff** it satisfies
all five: (1) a feasible alternative exists, (2) creating/maintaining it costs measured
labor/resources, (3) every flow has a counterpart and closes the conservation identity and is
auditable, (4) it is toggled by a scenario flag (never hardcoded always-on), and (5) an ablation
experiment with a pre-registered outcome exists. Anything failing the gate must instead be a
transparent *treatment* or stay out of the engine. Observatory labels remain read-only and must
never drive the engine.

Rationale: the research question in `MODEL_CHARTER.md` §1 is *about* credit/money/fiscal
capacity. Forbidding these outright would make the question unanswerable; allowing them without
the gate would reproduce the "rich artificial world" critique (REVIEW Appendix A). The gate keeps
the anti-hallucination guarantee (accounting) while enabling the science.

### C. Anti-teleology: no metric may directly cause an institution (conflict C3)

In `agrarian_transition_v1`, **no fixed year, Gini threshold, label, or milestone may directly
create** money, government, industrialization, redistribution, or a named social class.

Concretely for the existing `engine/politics.py` riot mechanism (`buoc_bao_dong`, gated on
`chinh_tri.gini_nguong_bao_dong`): it is **kept replayable for `preindustrial_closed_v1`** (legacy
benchmark) but is **scenario-gated OFF by default in `agrarian_transition_v1`**. The whole
political/fiscal layer (election, tax, minimum wage, bribery, unions, strike, riot) becomes a set
of **`experimental_treatment`s**, each requiring: an agent action, collective participation, a
declared cost, and a legal/accounting path. A Gini threshold may at most be one *necessary
condition among several that includes collective agent action* — it may never be the sole cause,
and the confiscation share/target/redistribution stays a transparent, ledger-backed treatment,
not a silent engine default. Redistribution studied as "emergent inequality" requires the
mechanical redistribution to be OFF (REVIEW §2.2.G, §4.8).

Config change (deferred to T08, recorded here): introduce `chinh_tri.bat` (or an equivalent
per-scenario institution-enable map) so the legacy scenario sets it `true` and
`agrarian_transition_v1` sets it `false`. No behavior of the legacy run changes; the new scenario
simply does not run the political layer unless a treatment overlay enables it.

### D. Determinism must cover new state (conflict C12, INVARIANT)

`world_hash()`/checkpoint must include every behavior-affecting field added since the original
spec: `ChinhQuyen` (votes, incumbent, term, tax rate, min wage, union set, strike set),
disease-shock state, survival-floor bookkeeping, entity/share state, and payment statistics. T02
audits this and adds a regression test: a run that exercises the political layer must replay to
the same hash. Any state that legitimately cannot enter the hash (e.g. external transcript) must
be reconstructable from a versioned artifact.

### E. Drop "median industrialization year" as a scientific criterion (conflict C6)

`CLAUDE.md` §8, `SPEC.md` row 10, `PHASES.md` Phase 4 define "success" as tuning the mock so the
median seed hits an industrialization label in year 160–280. This is **superseded** as a
*scientific* acceptance criterion (it is a pre-chosen target tuned to itself — REVIEW §2.2.C). It
may survive only as a **legacy regression label** on `preindustrial_closed_v1`, never as evidence
and never applied to `agrarian_transition_v1`.

### F. Two tracks, never cross-cited (conflict C9)

`preindustrial_closed_v1` = legacy mechanism/regression benchmark; `agrarian_transition_v1` = new
mechanism benchmark. `REPORTS.md` (the "Science/Nature/NeurIPS" manifesto) is marked as an
*aspirational proposal*, not evidence; its Gini>0.85→confiscation and "state formation" framings
are superseded by §C.

### G. Scenario shocks beyond weather (conflict C10)

`CLAUDE.md` §2 allowed *only* weather as a scripted exogenous event. The tree already ships a
`cu_soc.dich_benh` (disease) shock — **default OFF** (`config/world.yaml: dich_benh.bat: false`).
This is consistent with the transparent-institution gate: a shock is a scenario-flagged treatment
with declared magnitude/effect and provenance, not a hidden always-on event. The "only weather"
bullet is therefore **superseded** to: "exogenous shocks are scenario-flagged treatments,
default OFF, each with declared distribution/provenance; weather is the only shock ON by default."
Disease and any future shocks stay OFF in `agrarian_transition_v1` until T03/T08 give them
provenance + ablation.

## Consequences

- Positive: the science question becomes answerable without giving up conservation/replay; the
  worst overclaim risks (Gini→confiscation as "emergence", mock as empirical) are closed by
  policy; readers can tell engine-mechanism from scenario-assumption from observatory-label.
- Cost/work created: T02 (hash coverage + output isolation), T03 (scenario package + validation
  gate), T08 (scenario-gate the political layer), T09 (BehaviorPolicy split), T10 (ablation
  protocol). Each named institution now owes an ablation.
- Risk: scenario-gating the political layer must not change legacy replay hashes. Mitigation:
  default flags reproduce current behavior for `preindustrial_closed_v1`; regression test in T02.

## Compliance / test gate

A documentation+test gate is added (T01/T03): a scenario whose `validation_tier` is not
`empirical`, or whose in-sample/holdout targets or provenance are empty, **cannot** be printed or
exported with an `empirically_validated`/`validated`/`calibrated` label. `tools/validation.py`
already enforces `empirical_ready` on tier+targets+provenance; T03 extends it to reject empirical
wording and to check units/`design_assumption` status. See `tests/test_validation.py` and the
T01 gate test.
