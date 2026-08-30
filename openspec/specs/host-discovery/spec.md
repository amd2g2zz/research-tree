<!-- generated from openspec/changes/host-capability-discovery:PR #373 (#322) at alpha3-batch2-fixup-sync -->

## ADDED Requirements

### Requirement: host capability discovery is governed
Capability discovery records available files, shell, retrieval, persistence, delegation, experiment, and structured-input surfaces. Pi is a known host with a supported compatibility path.

#### Scenario: known host returns a structured manifest
- **WHEN** capability_manifest(host) is called for a known host
- **THEN** the result has the host name, a list of capabilities, and a fallback id

#### Scenario: unknown host is structured, not deflected
- **WHEN** the host is not in HOSTS
- **THEN** the discovery surface returns a structured record with bounded recon paths, not a user question
