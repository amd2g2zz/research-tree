## ADDED Requirements

### Requirement: Activation evidence has three states
The system MUST represent `discovered`, `static_ready`, or `live_verified`; discovery or static validation MUST NOT prove body injection.

#### Scenario: Static checks pass without live evidence
- **WHEN** package and target are current but no matching native response was verified
- **THEN** report `static_ready` and MUST NOT emit a live receipt

#### Scenario: Path or bare marker is supplied
- **WHEN** input is a root `SKILL.md` path, Markdown link, bare name, or non-native marker
- **THEN** report `activation_unverified`, name the required invocation, and MUST NOT claim live activation

### Requirement: Probes preserve host-native semantics
Probe construction MUST be side-effect free and independent for Codex, Claude Code, and Hermes; it MUST NOT launch a host, mutate config, or write a receipt.

#### Scenario: Codex probe
- **WHEN** constructing a Codex probe for a valid package/correlation
- **THEN** include `$research-tree` text and matching typed `skill` input in app-server `turn/start`

#### Scenario: Claude and Hermes probes
- **WHEN** constructing their probes
- **THEN** use each native `/research-tree` path and expose plugin-qualified Claude or `/skill research-tree` Hermes only as distinct alternatives

#### Scenario: Malformed identity
- **WHEN** typed input/marker is malformed, host differs, or activation material drifted
- **THEN** fail stably and MUST NOT emit a live receipt

### Requirement: Live receipts are bounded
Only an exact sentinel MAY create a receipt binding versions, host, safe correlation, relative package ref, package/body/sentinel digests, and explicit non-proof claims. It MUST exclude prompts, raw output, credentials, absolute user paths, and private reasoning.

#### Scenario: Exact sentinel
- **WHEN** a static-ready package returns the exact same-host/correlation/digest sentinel
- **THEN** return `live_verified` with a safe receipt

#### Scenario: Extra output or drift
- **WHEN** output adds text or package/body digest changed
- **THEN** reject it and MUST NOT retain raw output or create a receipt

### Requirement: Installation diagnostics are non-destructive
Setup MUST classify `missing`, `current`, `legacy`, `stale_link`, or `conflict`; status, probe, dry-run, and ordinary install MUST NOT rewrite stale/conflicting targets.

#### Scenario: Link is broken or points elsewhere
- **WHEN** a symlink/junction does not resolve to the selected package
- **THEN** report `stale_link`, preserve it, and require confirmed refresh

#### Scenario: Copy matches or differs
- **WHEN** a non-link target has an equal canonical payload
- **THEN** report `current`; otherwise report `conflict` and refuse overwrite

#### Scenario: Refresh creation fails
- **WHEN** confirmed stale-link refresh cannot create the new link
- **THEN** restore its prior target or fail without claiming current

### Requirement: Unavailable hosts do not pass parity
Release evidence MUST attempt each native host independently. Missing executables/surfaces MUST be `unavailable`, never successful parity evidence.

#### Scenario: Host executable is missing
- **WHEN** one supported executable cannot be resolved
- **THEN** record its stable unavailable capability while other hosts remain independently evaluable

#### Scenario: Generated package crosses host boundaries
- **WHEN** a package contains another host marker/path/material or differs from authoring source
- **THEN** package/parity checks MUST fail and MUST NOT record `live_verified`
