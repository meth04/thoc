# ADR 0008 — Entry into settlement and simultaneous common-land allocation

- Status: **Accepted (implemented treatment)** — 2026-07-15.
- Scope: `agrarian_transition_v1` only, activated solely by the ordered overlay stack ending in `spatial_livelihood_v5.yaml`.
- Relation: supplements ADR 0005 (spatial livelihood), ADR 0006 (agent interface and journal), and ADR 0007 (residence/estate). It does not reinterpret historical v1–v4 artifacts.

## Decision

At the founding of the v5 treatment, a living adult can submit an ordered request for a public residential lot (`dat_o`). All requests are observed before allocation. A seeded lottery resolves a collision at each preference rank; agent-ID application order cannot determine the winner.

A residential lot is only a permit to place one `nha` work order. It gives neither farm title, food, wood, labour, a completed house, nor an implied market value. The generic project ledger still requires the configured house recipe and only creates a house after materials and labour have been physically contributed. Until completion, the lot is a real residential coordinate but not productive land.

Public rice fields remain seasonal commons. When several feasible residents request the same unowned field in a sowing season, v5 resolves that conflict simultaneously with a separate seeded lottery. A field being continuously homesteaded is reserved to its current cultivator, so a later request cannot reset accumulated tenure. The resolver grants seasonal use, not permanent title; the existing homestead rule remains the only route to title.

The LLM interface exposes the lot action, a housing status tool, visible production opportunities, action results, P2P messaging, contracts, quotes, and a private feasibility card. The model remains the primary decision-maker. A transparent, configuration-gated survival floor may add a legal request or keep an already feasible project moving when an omitted decision would create a mechanical survival deadlock; it never creates inputs or output.

## Ordering and invariants

The v5 tick order is:

1. agents form plans and every action is preflighted;
2. residential-lot requests are resolved;
3. contested common fields are resolved, then a disclosed food-feasibility bridge can select an unused feasible field;
4. projects are registered, labour issued, and production/consumption proceed under the ordinary engine rules.

The mutable lot registry is included in the behavioural hash only when the `dat_o` gate is enabled. Map lots are created only under that gate, consume no extra RNG in legacy paths, and old checkpoints migrate to an empty registry rather than inferring rights.

An empty permit held by a dead resident is released. A lot whose location has a completed house remains occupied, including while the house asset is handled by the estate subsystem; this prevents a second house from being built on the same site. This ADR does not add a housing-market, demolition, inheritance-of-site, or transfer-of-permit mechanism. Those are future institutional treatments and must not be inferred from this permit.

## Scientific boundary

Lot supply, preference-list length, lottery allocation, and shelter threshold are design or institutional assumptions, recorded in `scenarios/agrarian_transition_v1/provenance.csv`. They are not historical calibration. Any result using v5 must report the full overlay stack, seed, policy/provider mode, survival-floor activation, and reproducibility manifest. A mock smoke is a mechanism test, not evidence that a real LLM population will make the same choices.

## Acceptance evidence

`tests/test_settlement_entry.py` covers legal lot entry, no resource minting, lottery variation across seeds, homestead protection, non-reissue of an occupied house site, prompt/tool exposure, and a local mock autonomy smoke. The full test suite is the compatibility gate; legacy scenarios keep the feature gate off.
