# Audit implementation tracker

Scope: implement the approved audit batches in order. No paid discovery unless
explicitly requested. Do not change the protected Appium action contract without
the repository's required design approval.

## Batch 1 — Trustworthiness (active)

- [ ] A01: visible assertions exclude hidden descendants and internal identifiers.
- [ ] A02: complete contract identity, exact verification coverage, replay input pinning.
- [ ] A03: successful discovery publication requires successful pytest teardown.
- [ ] A04: preserve validated target identity through execution (design review needed).
- [ ] A05: retain action attempts when execution or the following observation fails.

## Later batches — not started

- [ ] Batch 2: A06–A07, explicit local fixtures and faithful replay drafts.
- [ ] Batch 3: A08–A11, next-app readiness, observation, boundaries, privacy/usage.
- [ ] Batch 4: reproducibility, CI, documentation consolidation, deferred capabilities.

## Validation

Baseline: 76 offline tests passed. Live/provider tests are opt-in. Record results
and any migration limitations below as each change is verified.
