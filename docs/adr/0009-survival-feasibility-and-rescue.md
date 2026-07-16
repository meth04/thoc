# ADR 0009 — Survival feasibility, voluntary rescue, and shelter-floor v7

- Status: **Accepted (design)** — 2026-07-15.
- Independent reviewer: **model-architect, 2026-07-15**.
- Scope: successor treatment for `agrarian_transition_v1`, applied by a new
  `spatial_livelihood_v7.yaml` after v1→v6. The existing v6 overlay is the reproductive-timing
  treatment; this ADR does not overwrite it and does not reinterpret or modify `real15_v5`.
- Relation: narrows ADR 0008's survival-floor statement; reuses ADR 0003/0007 residence and
  provisioning boundaries, ADR 0005 work/contract primitives, and ADR 0006 capability/journal
  parity. Section 5 gives a v7-only ordering refinement to ADR 0008. No production/config/test or
  artifact change is made by this ADR.
- Claim tier: all new numbers and treatment choices below are **`design_assumption`**, not
  calibration or historical fact.

## 1. Findings that require a decision

| Finding | Evidence | Mechanism / minimal alternative |
|---|---|---|
| A0021 repeatedly chose fishing while the physical food balance was negative, then died with a house but no food. | `data/runs/real15_v5/transcript.jsonl:591-1006`; `events.jsonl:8707,12762,12799-12801`; `REPORT_REAL15_V5.md:104-126` | This is a search/information/provisioning failure, not proof of aggregate scarcity. Give factual net balances and a legal settlement path; do not transfer village stocks automatically. |
| The current household food-equivalent view omits meat and fish although consumption eats both. A0021's prompt could show `0.0kg` while listing fish in personal assets. | `engine/economy.py:40-60`; `engine/consumption.py:71-105`; artifact transcript above | Add one pure edible-food view shared by feasibility and consumption tests. Do not reuse plant spoilage blindly: meat/fish have separate decay at `engine/chan_nuoi.py:172-180`. |
| The current “card” is an instruction to “consider four parts”, not an action-level feasibility statement. | `minds/prompts.py:787-797,1000-1003` | Replace it under the v7 gate with facts only: stocks, rights, inputs, labor, timing, food-equivalent output and constraints. |
| Shelter v5 is effectively always on: threshold equals maximum health, lot entry is evaluated before the threshold, and its labor cap equals the nominal adult tick budget. | `spatial_livelihood_v5.yaml:28-33`; `minds/safety.py:202-232,258-281` | Gate every shelter-floor action, including lot requests, by food-first ordering, predicted health and residual labor. |
| Existing protocols already provide persistent state and accounting. P2P is information-only and arrives next tick; quotes escrow existing assets; oral contracts may transfer food at signing and contribute labor later in the same tick. | `engine/tick.py:114-166,189-206,295-321`; `engine/quotes.py:145-214,298-363`; `engine/board.py:58-97`; `engine/contracts.py:110-130,480-507` | Do not add `xin_ho_tro`, a rescue wallet, emergency mint, or a second negotiation engine. |
| The filename `spatial_livelihood_v6.yaml` is already occupied by reproductive timing, and current shelter injection runs inside `minds.orchestrator` before preflight/common-land allocation. | `scenarios/agrarian_transition_v1/spatial_livelihood_v6.yaml:1-19`; `minds/orchestrator.py:380-384`; `engine/tick.py:64-83` | Use v7, and place the v7 shelter decision after common-land allocation rather than claiming the current call site already provides food-first ordering. |
| Current `gop_cong` runs on the signing tick and again at `age == thoi_han`, while periodic transfers start at `age > 0`; therefore a “one-tick” oral exchange is not expressible unambiguously. Current contract settlement also has no generic physical reachability check. | `engine/contracts.py:372-373,401-418,480-507`; `engine/board.py:58-74`; `minds/prompts.py:699-711` | Version the generic contract schedule and physical-delivery rule in v7. Do not advertise a rescue path whose labor count or delivery boundary differs from execution. |

`real15_v5` is `diagnostic_only_unreplayable` (`REPORT_REAL15_V5.md:24-33`). A0021 therefore defines
an offline **regression fixture**, not a historical replay or empirical observation.

## 2. Decision unit, model boundaries and state ownership

1. **Behavioral boundary — the person decides.** A residence is the provisioning/consumption
   boundary, not a separate deciding agent. One person receives one card and may still choose no
   rescue, an infeasible action, or a dominated action.
2. **Accounting/institutional boundary — ownership remains individual.** Food, seed, house, land and
   payment assets retain their ledger/parcel owner. “Legally provisionable inside residence R” is
   separate from “owned by person A”. No pantry, rescue account, donor pool or named credit module is
   added. A deferred reciprocal transfer may later be classified as relational credit by the
   observatory, but the engine only sees generic clauses.
3. **Physical boundary — no aggregate-food or teleport shortcut.** Village/world stocks are never
   counted as accessible food. A house owned by a living member of the residence may satisfy the
   current shelter rule without transferring title; a house owned by another residence or an estate
   does not. This ADR does not add occupancy/capacity/tenancy semantics. Tangible food and labor
   settlement must pass the v7 physical-reachability predicate in §4.3.
4. **Information boundary — local facts only.** Outside the residence, the card may reveal only
   protocol-visible public offers, directed offers/messages already delivered, observed
   relationships and public market evidence. It may identify a potential counterparty but never
   reveal that person's exact private balance, willingness, future decision or guaranteed surplus.
5. **Owner/lifecycle.** Ownership/rights/stocks remain engine-owned; residence/provisioning remain
   `engine.household`; proposals/contracts remain `engine.board/contracts`; quotes/escrow remain
   `engine.quotes`; projects remain `engine.projects`. The feasibility objects in §3 are immutable,
   derived values with lifetime limited to one render/projection call. `minds` renders facts and may
   inject provenance-labelled intents, but never mutates `World` or settles a rescue.
6. **No new mutable survival state.** No request queue, rescue wallet, donor flag, RNG cache, id
   counter or checkpoint field is introduced. Existing board/contract/quote/project state keeps its
   existing owner and lifecycle.

## 3. Survival feasibility API and facts-only card

### 3.1 Pure engine API

Use a small physical-view module, not a household helper hidden inside prompts and not a mega-module:

```python
edible_assets(w: World) -> tuple[EdibleAssetSpec, ...]
build_survival_feasibility(w: World, aid: str) -> SurvivalFeasibility
project_post_plan_survival(
    w: World,
    residence_id: str,
    plans: Mapping[str, KeHoach],
    allocated_common_fields: AbstractSet[str],
) -> SurvivalProjection
```

Required output fields are versioned Pydantic/frozen schemas:

- `as_of_tick`, `phase="decision"|"post_common_land"`, `residence_id`, sorted `members`;
- `owned_by_person` and `provisionable_in_residence` as separate owner/asset rows;
- `food_open`, `decay_before_consumption`, `guaranteed_settled_inflow`,
  `guaranteed_feasible_output`, `seed_use`, `need`, `gap`, all by asset and in
  kg-thóc-equivalent;
- `labor_capacity`, `childcare_due`, `outgoing_contract_due`, `voluntary_requested`,
  `residual_conservative` for the rendered person;
- sorted production/quote/contract path rows with `visible`, `reachable`, `input_owner`,
  `earliest_output_tick`/`earliest_settlement_tick`, `gross_food`, `net_food`, and stable reason
  codes.

The API is read-only, consumes no RNG, allocates no id and writes no cache. The renderer receives the
schema and returns text/tool JSON only. Tests compare the schema, not fragile prose.

### 3.2 Food identity and uncertainty

`edible_assets` is the single source for nutritional conversion used by the card and by parity tests:

- `thoc` and enabled crops use `engine.economy.food_equivalence` factors;
- `thit` uses `chan_nuoi.thit_quy_doi_dinh_duong` and `thit_hao_moi_tick`;
- `ca` uses `danh_ca.ca_quy_doi_dinh_duong` and `ca_hao_moi_tick`.

Decay is projected **per owner and asset**, because plant storage technology may differ by owner.
The phase order is the existing one: production and settled contractual/quote inflows occur before
`hao_thit`/`hao_hut_kho`, then residence provisioning and consumption. The card must not apply both
plant spoilage and meat/fish decay to the same asset.

Only already-escrowed, due, reachable transfers and post-allocation actions with all owned inputs,
rights, season and conservative labor available enter `guaranteed_*`. A visible proposal, a pending
message, an unaccepted quote, fishing/foraging from a contested commons, or an active contract payer's
unreserved private balance is **conditional** and excluded from guaranteed food. It can appear as a
labelled path, never as food already available.

For the decision-time card, the trigger is:

```text
projected residence-provisionable food after deterministic decay
+ already-escrowed due inflow
< current-tick residence need
```

It is not a calibrated runway threshold. At post-plan shelter ordering, the same identity additionally
includes common fields already allocated and other conservative accepted outputs.

### 3.3 Required card content

When the trigger is true, render the expanded card; otherwise a compact balance is sufficient. The
expanded card contains, with explicit units:

- residence id/members; personal owner balances versus food legally provisionable in that residence;
- complete edible stock, owner-specific expected decay, need and current-tick gap;
- labor capacity, childcare, active outgoing-contract commitments, voluntary requested labor and
  conservative residual; labor is a non-storable tick flow, not wealth;
- for each locally feasible production action: season, target/right holder, land status
  (owned/common/contract-use), seed/material input and owner, labor input, earliest output tick,
  gross and net food equivalent; contested common parcels are conditional, not guaranteed;
- fish/forest/catch facts from the person's observable local stock/CPUE/access; crop facts from local
  soil, current weather, skill and active use/output-share clauses; no global profitability ranking
  and no engine-selected crop;
- visible quote/contract references, public terms, reachability/transport constraint, what must be
  escrowed or promised, and earliest settlement tick. Beliefs and observed prices remain labelled as
  beliefs/evidence.

Forbidden fields/text: `recommended`, `best`, occupation ranking, global-wallet surplus, invented
price/wage, exact outsider balances, or an assertion that help will arrive. Ordering is by
`(protocol, target_id, path_id)`. The card creates no state read by later behavior.

## 4. Voluntary rescue reuses generic protocols

### 4.1 Primary path for a person with no seed and no payment asset

Use a **public or directed oral contract proposal** composed from existing clauses:

- food now: `chuyen_giao_mot_lan` from responder to requester at `ky_ket`;
- optional reciprocity: `gop_cong` from requester to responder for a disclosed bounded duration;
- optional deferred reciprocity: a later `chuyen_giao_mot_lan` from requester to responder.

Oral form requires no literacy; only written/secured terms retain the literacy/collateral gate. A
one-way gift is legal only when a responder voluntarily accepts it; the engine never chooses a donor.
No module/action named rescue, loan, wage or charity is introduced.

### 4.2 Other existing paths

- **Quote/escrow** is for spot food purchase only when the requester already owns the payment asset.
  It is not the primary work-for-food path: quote posting locks an existing asset, while labor cannot
  be escrowed across ticks.
- **P2P** can identify or negotiate with a person visible under existing local facts, but is
  information only and cannot count as rescue until a ledger-settled quote/contract exists.
- **Within-residence provisioning** is counted first in the projection because it is legally
  provisionable under ADR 0007. The actual ledger transfer still occurs in the ordinary consumption
  phase; this ADR does not reorder consumption merely to make a report look earlier.

### 4.3 Contract timing, physical reachability and atomicity

The v7 contract schedule is generic and explicit:

- with `hop_dong.gop_cong_lich: signing_tick_half_open_v2`, a `gop_cong` clause executes when
  `0 <= w.tick - tick_ky < thoi_han`; `thoi_han=1` therefore means exactly one contribution on the
  signing tick; `thoi_han=None` continues until valid cancellation/default;
- the food-at-signing leg commits before phase-5 labor, so a contract accepted at `t+1` can transfer
  food and then contribute labor in that same tick;
- card/tool rendering discloses the exact ticks and total promised labor. Legacy overlays without
  this enum retain their prior schedule and hash.

With `hop_dong.tiep_can_vat_ly_v2: true`, every tangible `chuyen_giao_*` and `gop_cong` execution must
pass one shared pure predicate. The minimal v7 implementation permits same-residence or same-village,
same-bank handoff; a declared transport/delivery primitive may extend it later. A directed message or
directed offer may carry information farther, but cannot teleport food or labor. Failure returns
`delivery_unreachable`, moves nothing and leaves no active contract created from an unexecutable
signing leg.

All `ky_ket` transfers are one `Ledger.ap_dung(Transaction)` commit. Position tokens are created only
after that commit succeeds. A failed signing transaction creates neither partial food movement nor
contract/position state. The smaller alternative—sequential transfers followed by compensating
reverse transfers—is rejected because an exception between legs is not atomic and makes rollback
harder to test.

### 4.4 Response timing

No same-tick LLM sub-round is added. A proposal posted at tick `t` is first visible to eligible
responders at decision time `t+1`; acceptance at `t+1` transfers signing food in phase 4 before that
tick's consumption. It cannot rescue the requester's consumption at tick `t`. If the requester dies at
the end of `t`, the proposal is removed as a ghost offer.

If an independent fixture shows that a person alive at decision time must die before `t+1` although a
visible, willing, solvent and physically reachable responder exists, same-tick response becomes a
separate experimental treatment with transcript/budget/replay accounting. It is not smuggled into
this ADR.

### 4.5 Deterministic competition and failure

No rescue-specific winner rule is added. Board proposals are processed by proposal id; responders use
the existing relationship-first, seeded tie-break. Quote ids/fills and project ids keep their existing
sorted deterministic order. A responder can lose solvency to an earlier valid settlement; the later
acceptance then fails atomically. Expiry, death, insufficient food/payment/labor, unreachable delivery,
invalid clause or missing rights produce no transfer and no donor substitution.

## 5. Shelter-floor v7: exact ordering, threshold and labor

### 5.1 Config contract

The v7 overlay adds the following values; the existing reproductive v6 overlay remains earlier in the
stack:

| Parameter | Value | Unit | Status / rationale |
|---|---:|---|---|
| `minds.survival_feasibility.bat` | `true` | boolean | interface treatment, `design_assumption` |
| `minds.san_cho_o_toi_thieu.phien_ban` | `v7` | enum | treatment identity, `design_assumption` |
| `minds.san_cho_o_toi_thieu.nguong_health_khoi_cong` | `60` | health points | `design_assumption`; current physical health range is 0–100 |
| `minds.san_cho_o_toi_thieu.cong_gop_moi_tick` | `60` | công/tick | `design_assumption`; plus the stricter residual cap below |
| `hop_dong.gop_cong_lich` | `signing_tick_half_open_v2` | enum | generic contract-timing identity, `design_assumption` |
| `hop_dong.tiep_can_vat_ly_v2` | `true` | boolean | generic no-teleport settlement boundary, `design_assumption` |

The health maximum is not a new calibration parameter: current engine health is clamped to 100. The
validator must read a shared health-bound helper rather than duplicate another literal. Validation
rejects threshold outside `[0, health_max)`, labor cap outside `[0, nominal_healthy_adult_labor)`, an
unknown schedule enum, or negative values.

### 5.2 V7-only tick ordering

Current v5 resolves lots before common fields and invokes shelter inside the orchestrator. That cannot
satisfy “food after ordinary allocation uncertainty, then shelter”. Under v7 only, use this order:

1. minds compile voluntary person/entity plans; v7 decision cards are read-only;
2. engine preflights voluntary plans;
3. resolve contested common fields and apply the existing post-lottery food bridge;
4. derive `SurvivalProjection` from current state plus allocated fields and conservative voluntary
   requests;
5. if projected food at consumption remains below need, inject **no** shelter-floor action;
6. otherwise, if predicted end-of-tick health without shelter is `<= 60` and the residence has no
   usable house, the floor may inject lot/project/material/logging/labor intents;
7. journal and preflight only the newly injected intents with origin `survival_floor`;
8. resolve all voluntary plus floor residential-lot requests simultaneously, then register projects;
9. continue the ordinary phase-4→consumption pipeline.

This is a narrow v7 refinement of ADR 0008 §Ordering. The lot and common-land lotteries use isolated
keyed RNG streams, so their relative call-site order must not alter either draw. Gate OFF retains the
v5/v6 ordering exactly.

`predicted end-of-tick health without shelter` uses the same current-tick food ratio, aging loss,
homeless exposure, known disease shock and health clamps as consumption/demography, but excludes any
benefit from the shelter intent being considered. Random mortality is not predicted as certainty.

### 5.3 Residual labor and non-interference

The floor never cancels/reduces a voluntary action. Its conservative residual is:

```text
own labor capacity
− mandatory childcare
− active outgoing gop_cong due under the v7 schedule
− all voluntary labor requested by this person in actual execution priority
− post-lottery food-floor labor
```

Unsettled incoming labor/food and labor that another person merely promised are zero in this
calculation. Total **incremental** shelter-floor labor across logging plus project contribution is:

```text
min(60, residual_conservative)
```

Only the delta injected by the floor counts as floor labor; pre-existing voluntary labor remains its
original provenance. Material contribution may move only material already owned and is escrowed by
the generic project primitive. If wood is missing, logging can occur this tick but the project can use
that wood only according to ordinary phase order; the floor does not manufacture same-tick completion.

The floor never starts a rescue contract, selects a counterparty, fabricates a responder, cancels a
livelihood plan, or counts house/food across the wrong residence boundary.

## 6. Ledger/FlowRegistry identity, failure and rollback

| Mechanism | Ledger identity | FlowRegistry | Failure / rollback |
|---|---|---|---|
| Card/projection | no transaction | none | pure call; schema/renderer failure omits expanded card and records an interface error, never mutates World |
| Food at signing | one balanced `Transaction`: responder food `−q`, requester food `+q` | none; ownership transfer is not source/sink | whole transaction rejects; no contract id/position token |
| Contract positions | existing `vi_the:<hd>:<ben>` mint at successful signing, burn at closure | existing `ky_hd` source / `het_hd` sink | created only after signing commit; closure burns exactly once |
| `gop_cong` | requester `cong −q`, responder `cong +q`; later use/evaporation follows ordinary labor physics | transfer itself none; existing `cong/dung` or `cong/boc_hoi` closes labor | insufficient/unreachable contribution follows ordinary breach rule; no negative balance |
| Deferred reciprocal food | balanced transfer at declared due tick | none | insufficient/unreachable payer produces explicit failure/default; no mint and no heir debt |
| Quote path | existing two-sided escrow transaction | none | existing exact-once settlement/refund; requester without payment cannot enter escrow |
| Shelter project | existing material escrow; labor burn; recipe input sink/output source | existing project-configured flows | cancellation refunds held material to original contributors; spent labor is not refunded |

Audit runs at the ordinary end-of-tick point. No new source/sink is registered by this ADR.

## 7. Config provenance, alternatives, ablation and predicted signs

Create `spatial_livelihood_v7.yaml`; do not edit base config or v1–v6 overlays. Add all six rows in
§5.1 to `scenarios/agrarian_transition_v1/provenance.csv`, with units, empty source and status
`design_assumption`. Manifest/scope records `survival_feasibility_v7`, `shelter_floor_v7`,
`contract_schedule_v2` and `physical_contract_delivery_v2` separately from LLM decisions.

**Smaller alternatives considered:**

1. Prompt wording only, no physical card schema — rejected because formulas drift and cannot be parity
   tested against consumption.
2. Add `xin_ho_tro`/rescue wallet — rejected because it duplicates board/contracts and risks an
   engine-selected donor or absorbing account.
3. Keep current contract timing/reachability and only advertise oral rescue — rejected because the
   interface would promise a one-tick/local exchange that execution cannot represent.
4. Same-tick LLM response sub-round — deferred; current evidence does not establish necessity and it
   adds budget/transcript/scheduler state.

Paired-seed offline ablation is `card {OFF,ON} × shelter_floor {OFF,v7}`. Contract schedule/delivery v2
remain fixed across those four cells as infrastructure truth; compare v6 separately to measure that
infrastructure change. Pre-register:

- card ON should weakly reduce repeated actions whose displayed net current-tick food balance is
  negative and weakly increase attempts/settlements through visible feasible paths;
- shelter v7 should reduce floor labor among food-insecure residences and may delay house completion
  or increase exposure; it must not mechanically improve every welfare outcome;
- more visible local food offers, lower transport barriers, or more responder-owned food should weakly
  expand the feasible settled-rescue set. No willing/solvent/reachable responder means no transfer;
- lower fish stock/CPUE must not increase displayed fish output. More land/labor expands feasible
  production only when seed, rights, season and access also permit it;
- `thoi_han=1` under schedule v2 must create exactly one signing-tick labor contribution; schedule OFF
  reproduces legacy timing.

Failure of these signs is a mechanism finding; parameters are not retuned to force them.

## 8. Serialization, world hash, replay and migration

- Feasibility/card objects are ephemeral derived views: no World field, id counter, RNG draw,
  checkpoint field or hash block is added. Their schema version, config, prompt/catalog/tool version
  are behavioral identities in config digest, prompt hash, capability hash, manifest and transcript.
- Existing board/contracts/messages are already in `behavioral_state()`; gated quotes and projects
  are included when enabled (`engine/world.py:687-710,784-804`). Rescue adds no parallel state.
- V7 config is a different experiment and may produce a different world hash. Without v7 overlay,
  v1–v6 behavior/hash and the reproductive v6 file are unchanged.
- `_behavioral_config` must normalize `minds.survival_feasibility.bat:false` and a disabled shelter
  block to absent. The v7 contract enums are retained whenever enabled because they change the
  transition function.
- No checkpoint field migration or hash-schema bump is required. A v7 run starts fresh; resume with a
  different overlay fails closed by config digest. Old checkpoints infer neither rescue requests,
  rights nor contract timing.
- Acceptance requires same seed+overlay+transcript replay with zero transcript misses/unused rows and
  the same final hash. A checkpoint between proposal and response must preserve board state and resume
  to the same acceptance/settlement. The unreplayable A0021 artifact is never patched.

## 9. Required deterministic test matrix

The A0021 fixture uses quantities only to enforce inequalities (`catch_food < need`, no seed/payment,
local responder food); all fixture numbers are test `design_assumption`, not historical facts.

| ID | Required test / invariant |
|---|---|
| S1 | **Food identity:** card/projection and consumption agree for thóc/crops/meat/fish, owner-specific decay and phase ordering; opening + settled inflow + guaranteed output − seed − decay − need closes by asset/equivalent without double counting. |
| S2 | **Boundary:** requester in R1 cannot count exact food in R2 or an estate. Moving responder into R1 activates only ADR 0007 provisioning; house ownership and food provisioning remain separate fields. |
| S3 | **Facts-only/API:** no seed + low CPUE marks rice infeasible and fishing conditional/net-below-need; no recommendation/rank/global balance appears. Schema order is stable and render consumes no RNG. |
| S4 | **Oral timing:** proposal at `t`, acceptance at `t+1`; one atomic food transfer precedes consumption; `thoi_han=1` contributes labor exactly once on signing tick; balances/audit close and no food/labor is minted. |
| S5 | **Countercases:** no responder, insufficient food, expired offer, dead party, visibility failure or physical-unreachability produces no transfer/position token. Requester may die; card/floor does not fabricate a donor. |
| S6 | **Quote distinction:** requester with payment can settle a visible food quote through both escrows; requester without payment cannot use quote as phantom credit and sees only truthful protocol requirements. |
| S7 | **Shelter order/cap:** food-deficit residence gets zero floor lot/logging/project action; food-secure residence triggers only at predicted health `<=60`; injected labor is `<=min(60,residual)` and provenance is `survival_floor`, never `llm`. |
| S8 | **Non-interference:** voluntary plans are never reduced/reordered by the floor; only incremental floor deltas carry floor provenance; injected actions receive request/preflight/terminal journal rows. |
| S9 | **Ordering/tie-break:** common-field allocation precedes v7 shelter evaluation, then all lot requests resolve simultaneously; keyed lottery outcomes do not change merely because call-site order changed; board multi-responder outcome is deterministic. |
| S10 | **Atomic failure:** one signing leg short, reachability false, or injected exception leaves all signing balances, contract registry, id counters and position tokens unchanged. |
| S11 | **Determinism/replay:** same-seed offline runs match; checkpoint between proposal and response resumes to the same settlement/hash; transcript replay has zero miss/unused; OFF retains pinned v1–v6 hashes. |
| S12 | **Timing limit/artifact boundary:** no same-tick response is assumed; a synthetic “must die before t+1” case remains a documented failure. Tests reconstruct A0021 inequalities without loading/modifying the diagnostic artifact or making empirical mortality claims. |

Tests S1–S3/S7–S10 are engine/rulebot fixtures. S4–S6 include direct deterministic plans; a separate
mock/FakeTransport test verifies that the card/capability surface can express them. Passing does not
require or prove that an LLM chooses rescue.

## 10. Claim boundary and handoff

Passing this ADR establishes only that a person can observe truthful local survival constraints and
that existing generic protocols can represent a voluntary, physically reachable, ledger-settled path.
It does **not** establish that neighbors will help, that starvation is historically realistic, that
aggregate abundance implies individual food security, or that a real LLM will use the path.

### Engine implementation plan

1. Add the pure edible/feasibility schemas and projections; reuse consumption/decay helpers rather than
   copy formulas.
2. Add generic contract schedule v2, physical reachability and one-transaction signing; preserve
   legacy behavior when v7 keys are absent.
3. Move only v7 shelter injection to the §5.2 tick point; journal/preflight injected deltas; retain
   current v5/v6 call order when gate off.
4. Add v7 overlay/provenance/manifest identity and behavioral-config normalization. Do not add rescue
   state/action/account, donor selection, price, wage or free resource.

### Minds implementation plan

1. Render the immutable schema as facts-only text/tool JSON; remove the v7 path's imperative survival
   prose and duplicate household-food calculation.
2. Expose only protocol-visible ids/terms and exact contract timing; never expose outsider balances or
   claim willingness/solvency.
3. Keep LLM/policy output as ordinary contract/message/quote/project intents. Floor intents retain
   separate provenance and never count as LLM autonomy.

### Test-engineer contract

Implement S1–S12 independently, including property tests for food identity/atomic rollback, negative
information/reachability cases, OFF hash pins, interrupted-resume replay and action-journal terminal
coverage. Do not self-approve implementation tests and do not require a favorable welfare result.

### QA/reviewer questions

1. Does any card field leak exact outsider assets, global stock, future willingness or a hidden ranking?
2. Can any food/labor leg cross residence/village/bank without provisioning, escrow or declared
   reachability?
3. Is `thoi_han=1` exactly one labor tick under v7, and unchanged under earlier overlays?
4. Can a failed signing create an id gap, position token, partial transfer or compensating mint?
5. Is shelter evaluated after common-land uncertainty and before lot resolution only when v7 is on?
6. Are residual labor and provenance computed from incremental floor deltas rather than total plans?
7. Do v1–v6, especially the existing reproductive v6 overlay, retain filenames, config identity and
   pinned OFF hashes?
8. Do replay/manifest identities distinguish card, shelter, contract timing and delivery treatments?
