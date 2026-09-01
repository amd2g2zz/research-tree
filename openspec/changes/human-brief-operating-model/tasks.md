# Tasks

## 1. Delivery data plane

- [ ] 1.1 Add the `operating_model` block (schema 1) to the compiled Human
      Brief document: roles, outcome layers, blockers, fallback plan, and
      baseline-run dimensions with named-field validation.
- [ ] 1.2 Source outcome layers from real artifacts: `latest_confirmed`
      projection with the #450 authority fingerprint, per-oracle
      `goal_satisfaction` registrations, goal-contribution assessments.
- [ ] 1.3 Mirror `why_not_complete` resolve entries as blockers with owner
      roles; disclose an absent coordinator state explicitly.

## 2. Template

- [ ] 2.1 Restructure `assets/human-brief-template.md` around the seven
      operating-model fields, preserving the pre-existing semantic sections.
- [ ] 2.2 Regenerate host packages and keep the generated-only commit
      separate.

## 3. Documentation

- [ ] 3.1 PRODUCT.md §4.2 and §7.2 reference the operating-model fields with
      the baseline-run framing.

## 4. Validation

- [ ] 4.1 Red-green tests for the payload validator (positive + named-error
      negatives), artifact sourcing, rendering, and the template structure.
