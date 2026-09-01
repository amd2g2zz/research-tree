# Design

`EvidenceArtifact` records an immutable content digest, acquisition metadata,
media type, provenance group, applicability, confidence, limitations, and
source locator. `EvidenceAnchor` records the exact artifact revision plus a
typed selector for lines, symbols, fragments, document sections, image regions,
input revisions, or experiment fields.

`EvidenceResolver` verifies the artifact exists in the workspace CAS, has the
declared size and SHA-256 digest, is active, and matches the anchor extractor
version. Repository path locators are constrained to the configured workspace.
URL derivatives are grouped by origin/provenance rather than counted as
independent sources.

OracleRun, closure, coordinator policy, and report rendering are out of scope
for this issue and remain owned by the later Alpha2 issues.
