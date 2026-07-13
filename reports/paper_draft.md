# Whose Institutions? Measuring Decision-Maker Effects in a Constraint-Accounted LLM Agent-Based Model

**Draft v0.1 — 2026-07-13.** Status: working draft for an AI/computational-social-science venue
(NeurIPS Datasets & Benchmarks / AAMAS / ICWSM / Computational Economics). Claim tier throughout:
**mechanism benchmark + methodology**, NOT empirical economics. Numbers marked `[PENDING_COMPUTE]`
require a multi-model ≥30-seed ensemble not yet run; they are placeholders, never fabricated.

---

## Abstract

Large-language-model agent-based models (LLM-ABMs) increasingly report the "spontaneous emergence"
of economic institutions (markets, contracts, credit, money, government). We argue that such claims
are often **unidentified**: they cannot separate the contribution of the *environment* from that of
the *decision-maker* (the heuristic, LLM, or random policy that chooses actions). We present THÓC, an
LLM-ABM built on three auditable primitives — a double-entry ledger with per-tick conservation audit,
an action-validation compiler that lets agents only *propose* intents the engine feasibility-checks,
and a deterministic replay tree — and a micro-task benchmark with engine-computed ground truth. These
let us hold the environment fixed and vary only the decision-maker. In a pre-industrial agrarian
scenario, a rich institutional economy (337 active contracts, land inequality, 93% literacy) emerges
**only** under a contract-aware heuristic; under feasible-random, subsistence, and adaptive-
expectations policies, **zero** contracts form and the population nearly collapses. A pilot with a
real LLM (Gemini) behaves like the simple baselines (≈0 contracts) rather than the contract-aware
heuristic, and diverges sharply from a heuristic "mock" often used as an LLM stand-in. We conclude
that institutional "emergence" in this class of models is largely a property of the decision-maker,
not the world, and release a reproducible, non-network benchmark (one-command replay; transcript-
based replay for real runs) to make such effects measurable.

## 1. Introduction

LLM agents are increasingly used to "grow" artificial societies and read off emergent macro-phenomena.
A recurring narrative is that institutions arise spontaneously from micro-interactions. But an ABM's
macro output is a joint function of (i) the physical/accounting environment, (ii) the institutional
rules that are on, and (iii) the *decision-maker* that selects actions. If (iii) is a hand-tuned
heuristic that already knows the target institutions, "emergence" may be an artifact of the heuristic,
not of the world. Prior LLM-ABM work rarely isolates (iii): it reports one decision-maker (often an
LLM, or a heuristic proxy for one) and one or few seeds, without a controlled comparison or a
ground-truth benchmark.

**Contributions.** (1) A **constraint-accounted LLM-ABM** whose ledger + action-validation + replay
make every asset/debt/money flow auditable and every run bit-reproducible, so the decision-maker can
be swapped with everything else fixed. (2) A **micro-task benchmark** with engine-computed ground
truth (constraint-following, contract-execution, no-selling-unowned, shock-response) that scores any
decision-maker on feasibility, welfare-regret, action-diversity, and (for LLMs) fallback/cost. (3) A
**decision-maker identification result**: institutions emerge only under a contract-aware heuristic;
simpler policies and a real LLM produce none. (4) A **reproducible, non-network artifact** with a
claim-tier gate that refuses "empirical/validated" labels without data.

## 2. Related work (to expand)

LLM agent societies (generative-agent simulations, economic LLM-ABMs); classical ABM in economics
and the identification critique; reproducibility and benchmarking for LLM agents. Key contrast: we
treat the LLM as a *treatment* with measurable error, not as ground-truth behavior (cf. REVIEW.md).

## 3. System

**Physical + accounting layer (invariant).** A 30×30 seeded map with land, seasons, storage, labor,
and weather. Every asset/debt/money movement is a double-entry ledger transaction registered in a
FlowRegistry; an audit asserts conservation *after every tick* and halts on violation. Debt is a
contract obligation, never a negative balance.

**Action-validation.** Decision-makers (heuristic, LLM, random) return only *intents*; the engine
validates each against a feasibility whitelist before applying, in a deterministic sorted order.
Invalid intents are logged and dropped, never crash the run. Institutions (rent, hire, credit, money,
fiscal, ferry) are **not** named engine code but combinations of a 9-clause contract grammar + assets;
labels are attached read-only by an observatory and never drive the engine.

**Determinism + replay.** A single RNG tree (SeedSequence per subsystem×tick) makes runs
bit-reproducible: same seed + same transcript → same world-hash. Rulebot/mock replay from seed;
real replay from a lossless, key-masked transcript (`--from-transcript`) reproduces the exact action
trace and world-hash without network. A verifier tool re-runs and audits any run and returns nonzero
if evidence is missing.

**Scope discipline.** Every new mechanism is scenario-gated (off by default), preserving legacy
world-hash/replay when off (verified: pre-change runs replay to identical hashes). A validation gate
refuses `empirical/validated` claim labels unless real targets + holdout + real provenance exist.

## 4. Benchmark

**Scenario `agrarian_transition_v1`** (mechanism_benchmark): a hypothetical partly-closed agrarian
community; households are the economic unit; layers (market, credit, money, fiscal, spatial) toggle by
overlay; the political/riot layer is off (no Gini-triggered redistribution — anti-teleology).

**Micro-tasks (engine-computed ground truth), `tools/microtasks.py`:**
(a) *constraint-following* — the feasible farming set from budget/seed/labor; (b) *contract-execution*
— honoring active clauses when solvent; (c) *no-selling-unowned* — orders bounded by ledger balances;
(d) *shock-response* — correct sign of reaction to drought/flood. Metrics per decision-maker:
constraint-violation-rate, feasible-rate, shock-correct-sign-rate, action-diversity (Shannon), and
(LLM) fallback-rate, cost/token. Ground truth is computed from world state independent of policy
output; the harness is verified to catch violations via synthetic over-reach policies.

## 5. Experimental protocol (pre-registered)

`scenarios/agrarian_transition_v1/preanalysis_protocol.yaml` locks question, seed list, horizon,
decision-maker set, expected signs + falsifiers, failed-run handling, and no-claim conditions before
the full ensemble. Reported here: local (non-network) decision-makers at n=3–5 seeds; the full
**≥30-seed × ≥2-model** ensemble with paired CIs is `[PENDING_COMPUTE]`.

## 6. Results

### 6.1 Institutions are a decision-maker effect (E1)
Same scenario, same seeds {41,42,43}, 100 ticks; only the decision-maker varies:

| decision-maker | population | land-Gini | active contracts | motifs | literacy |
|---|---:|---:|---:|---:|---:|
| rulebot (contract-aware) | 235 | 0.73 | **337** | 7 | 93% |
| feasible_random | 12 | 0.03 | **0** | 0 | 14% |
| subsistence | 15 | 0.00 | **0** | 0 | 17% |
| adaptive-expectations | 15 | 0.00 | **0** | 0 | 17% |

A rich contract economy and inequality appear *only* under the heuristic explicitly endowed with 8
contract templates; the others form no contracts and nearly collapse. The gap (337 vs 0) is the point.

### 6.2 The accounting layer enforces feasibility; behavior still differs (E2)
On the micro-task benchmark (n=5 seeds), all four baselines have **0% hard-constraint violations** —
the ledger + action-validation prevent infeasible/ownership-violating actions regardless of decision-
maker. Decision-makers differ on **action-diversity** (rulebot 2.14 bit > adaptive 1.54 ≈
feasible_random 1.56 > subsistence 0.99) and **shock-response** (only adaptive reacts with correct
sign). The benchmark's LLM slots (constraint-violation, fallback, cost) are wired and ready.

### 6.3 A real LLM behaves unlike its heuristic proxy (pilot)
A 50-year real-LLM run (Gemini, 1347 calls, 0% fallback, ~$1.03) produced ≈0 active contracts and a
contracting population (50→21) — resembling the simple baselines, not the contract-aware heuristic. A
matched "mock" heuristic (PersonaBot) instead produced 271 contracts and a growing population
(50→203). **The mock is not a proxy for LLM behavior**, and the "emergent institutions" seen under the
mock do not reproduce under the real LLM at this seed. A second real run on the benchmark scenario
(`real50_agr`, partial: 46/100 ticks, stopped gracefully by the budget guard on an upstream outage)
independently shows the same pattern — 2 active contracts, 0 firms, 12% literacy — versus rulebot's
337 and mock's 271. (n=1–2 per mode; `[PENDING_COMPUTE]` for the multi-model ≥30-seed version.)

### 6.4 Robustness / fragility
A 3-seed spatial on/off ablation shows the macro effect of an added spatial-ferry economy is within
seed noise, and ferry adoption itself is highly seed-dependent (0 to 42 crossings across seeds) —
emergence is fragile, motivating many-seed reporting over single-seed narratives.

## 7. Reproducibility & release

One-command non-network verification (`tools/verify_local`); per-run manifest with config/scenario
hashes, seed, git revision, and (for LLM) prompt-template/model/temperature hashes; `verify_research_
run` replays + audits any run; real/mock runs replay from a lossless key-masked transcript. All
baselines reproduce with zero network. **Concrete demonstration (mock AND real).** A full 50-year mock run (`mock50_agr`, 4267 LLM calls,
0% fallback) replays *from its transcript* to the identical world-hash `0135fa05…` with zero network
and zero missed calls. More importantly, a **real** Gemini run (`real50_agr`, 649 calls including 3
repaired/fallback responses) replays *from its transcript* to the identical world-hash `a2e06edd…`
with zero network — i.e. **a real LLM run is bit-reproducible from an audited transcript**, including
the repair/fallback path. To our knowledge this closes a reproducibility gap common to LLM-ABM work
(where real runs cannot be re-derived). Artifact: engine + scenario package + benchmark + seeds +
protocol; 299 tests pass under a network-blocking guard.

## 8. Limitations (must state)

Single simulated world (not calibrated to real data → no empirical/causal claim); prompt/model/
temperature are large assumptions; results are single-context; n is small pending the full ensemble;
MCP tool-round replay is mechanism-correct but not automated-tested; rulebot's advantage is partly by
construction (it knows the contract templates) — the identified quantity is the *magnitude* of the
decision-maker gap and the real-LLM's position relative to baselines.

## 9. Conclusion

In a constraint-accounted LLM-ABM, "institutional emergence" is chiefly a property of the decision-
maker, not the environment. Auditable accounting + replay + a ground-truth benchmark make this
measurable and reproducible. We release the benchmark and call for decision-maker-controlled, many-
seed, multi-model evaluation before attributing emergent institutions to LLM societies.

---

### Appendix: what remains before submission (honest gate; see `reports/publication_roadmap.md`)
- [ ] `[PENDING_COMPUTE]` E1/E2/6.3 at ≥30 seeds × ≥2 LLM models, paired CIs.
- [ ] Multi-provider config + live-real transcript captured & replayed.
- [ ] Registered ablations (accounting/validation/memory/contract-language) run and reported.
- [ ] Sensitivity (Morris/Sobol) parameter-importance table.
- [ ] Related-work section; figures auto-generated from raw metrics.
- [ ] Independent QA (adversarial-reviewer + reproducibility-steward) on the final draft + numbers.
