## Context

PR #207 deliberately retained `src/research_tree/scheduler.py` as private,
unreachable source so its public-surface deletion stayed within the CI review
limit. The module now has no runtime caller or root export, but its physical
presence and `RT-010` public contract falsely imply an available API.

## Goals / Non-Goals

**Goals:**

- Remove the retired implementation and obsolete public contract completely.
- Turn the transitional #178 regression into an absence check covering runtime
  imports and generated packages.
- Retain #178's historical OpenSpec change as delivery evidence rather than
  rewriting history.

**Non-Goals:**

- A replacement scheduler, compatibility namespace, alias, bridge, adapter,
  migration, fallback reader, or user-data operation.
- Changes to the shared Alpha2 group registry, receipt state, or parent #175
  closure.
- Removing generic uses of the word "scheduler" unrelated to the retired
  RunStore implementation.

## Decisions

### Delete the implementation instead of making it more private

The source has no supported caller after #178, so deleting the module is the
only current-only outcome. Keeping it behind an underscore or a compatibility
namespace would preserve a discoverable legacy writer.

### Delete the obsolete public contract

`docs/specs/RT-010.md` is marked "Accepted for implementation" and documents
the retired public API. It is a current contract, not immutable delivery
history, so removal is required. The prior #178 change artifacts stay intact
because they document why the two slices were sequenced.

### Use one focused structural regression

The existing retirement test already parses runtime imports and current
authority. It will assert source absence and scan generated packages for the
retired module or symbols. This catches accidental reintroduction without
testing an API that must no longer exist.

## Risks / Trade-offs

- [A dormant external consumer imported the removed module] -> This is an
  intentional breaking current-only removal; no compatibility path is added.
- [Historical OpenSpec text contains scheduler terms] -> The regression limits
  its active-contract check to current sources and leaves merged delivery
  records immutable.
- [No group is allocated for #179] -> Do not alter the shared registry in this
  branch; request the release-train owner to allocate the receipt separately.
