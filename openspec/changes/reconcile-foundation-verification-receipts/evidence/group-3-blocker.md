# Group 3 Blocker

Group 3 is intentionally not verified by this reconciliation. The current
evidence implementation accepts legacy `{kind, ref}` anchors by default and
does not persist an exact EvidenceArtifact ArtifactRef through the canonical
ledger. Delivery still validates the legacy anchor shape. These gaps are
tracked by successor issue #106 and must be fixed before group 3 or its
dependent group 4 can be verified.
