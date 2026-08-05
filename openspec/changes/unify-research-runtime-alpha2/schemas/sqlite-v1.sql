-- Alpha2 workspace ledger schema v1.
-- The coordinator is the only writer of canonical lifecycle state.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;

CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL,
  migration_digest TEXT NOT NULL UNIQUE
);

CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('alignment', 'handoff_pending', 'autonomous_research', 'synthesis', 'readiness', 'delivery_pending', 'awaiting_acceptance', 'completed', 'paused', 'blocked', 'superseded', 'authority_blocked', 'failed')),
  revision INTEGER NOT NULL,
  parent_run_id TEXT REFERENCES runs(run_id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  state_digest TEXT NOT NULL,
  authority_digest TEXT NOT NULL,
  termination_reason TEXT,
  UNIQUE(run_id, revision)
);

CREATE TABLE artifacts (
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  artifact_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  kind TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  actor_kind TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  PRIMARY KEY(run_id, artifact_id, revision),
  UNIQUE(run_id, content_hash)
);

CREATE TABLE artifact_parents (
  run_id TEXT NOT NULL,
  artifact_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  parent_run_id TEXT NOT NULL,
  parent_artifact_id TEXT NOT NULL,
  parent_revision INTEGER NOT NULL,
  PRIMARY KEY(run_id, artifact_id, revision, parent_run_id, parent_artifact_id, parent_revision),
  FOREIGN KEY(run_id, artifact_id, revision) REFERENCES artifacts(run_id, artifact_id, revision),
  FOREIGN KEY(parent_run_id, parent_artifact_id, parent_revision)
    REFERENCES artifacts(run_id, artifact_id, revision)
);

CREATE TABLE events (
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  event_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  causation_id TEXT,
  correlation_id TEXT,
  expected_revision INTEGER NOT NULL,
  emitted_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  accepted INTEGER NOT NULL,
  error_code TEXT,
  PRIMARY KEY(run_id, event_id),
  UNIQUE(run_id, sequence)
);

CREATE TABLE attempts (
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  attempt_id TEXT NOT NULL,
  work_item_id TEXT NOT NULL,
  action_id TEXT NOT NULL,
  host TEXT NOT NULL,
  status TEXT NOT NULL,
  dispatch_digest TEXT NOT NULL,
  retry_ordinal INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  terminal_at TEXT,
  PRIMARY KEY(run_id, attempt_id)
);

CREATE TABLE leases (
  run_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  owner TEXT NOT NULL,
  lease_expires_at TEXT NOT NULL,
  heartbeat_sequence INTEGER NOT NULL,
  last_seen_at TEXT,
  PRIMARY KEY(run_id, attempt_id),
  FOREIGN KEY(run_id, attempt_id) REFERENCES attempts(run_id, attempt_id)
);

CREATE TABLE evidence (
  run_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  artifact_digest TEXT NOT NULL,
  provenance_group TEXT NOT NULL,
  media_type TEXT NOT NULL,
  selector_json TEXT NOT NULL,
  acquisition_json TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY(run_id, evidence_id, revision),
  FOREIGN KEY(run_id, evidence_id, revision) REFERENCES artifacts(run_id, artifact_id, revision)
);

CREATE TABLE oracles (
  run_id TEXT NOT NULL,
  oracle_run_id TEXT NOT NULL,
  oracle_spec_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  verdict TEXT NOT NULL,
  environment_digest TEXT NOT NULL,
  toolchain_digest TEXT NOT NULL,
  result_json TEXT NOT NULL,
  reproducibility_status TEXT NOT NULL,
  PRIMARY KEY(run_id, oracle_run_id),
  FOREIGN KEY(run_id, attempt_id) REFERENCES attempts(run_id, attempt_id)
);

CREATE TABLE closures (
  run_id TEXT NOT NULL,
  slot_id TEXT NOT NULL,
  assessment_revision INTEGER NOT NULL,
  token_digest TEXT,
  status TEXT NOT NULL,
  input_refs_json TEXT NOT NULL,
  checks_json TEXT NOT NULL,
  issued_at TEXT,
  expires_at TEXT,
  PRIMARY KEY(run_id, slot_id, assessment_revision)
);

CREATE TABLE insights (
  run_id TEXT NOT NULL,
  digest_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  PRIMARY KEY(run_id, digest_id, revision)
);

CREATE TABLE host_events (
  run_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  protocol_version INTEGER NOT NULL,
  host TEXT NOT NULL,
  round_id TEXT NOT NULL,
  attempt_id TEXT,
  event_json TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  PRIMARY KEY(run_id, event_id),
  FOREIGN KEY(run_id, event_id) REFERENCES events(run_id, event_id)
);

CREATE TABLE deliveries (
  run_id TEXT NOT NULL,
  delivery_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  revision INTEGER NOT NULL,
  source_ledger_digest TEXT NOT NULL,
  compiler_version TEXT NOT NULL,
  template_version TEXT NOT NULL,
  output_digest TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  PRIMARY KEY(run_id, delivery_id, revision)
);

CREATE TABLE acceptances (
  run_id TEXT NOT NULL,
  acceptance_id TEXT NOT NULL,
  technical_revision TEXT NOT NULL,
  human_revision TEXT NOT NULL,
  displayed_digest TEXT NOT NULL,
  decision TEXT NOT NULL,
  feedback_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(run_id, acceptance_id)
);

CREATE TABLE migrations (
  migration_id TEXT PRIMARY KEY,
  operation TEXT NOT NULL CHECK (operation IN ('inventory', 'dry_run', 'apply', 'verify', 'rollback', 'status')),
  source_kind TEXT NOT NULL,
  source_locator TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  disposition TEXT NOT NULL,
  destination_refs_json TEXT NOT NULL,
  collision_json TEXT,
  operator_confirmation TEXT,
  rollback_of TEXT REFERENCES migrations(migration_id),
  created_at TEXT NOT NULL,
  UNIQUE(source_kind, source_locator, source_digest)
);

CREATE TABLE audit_exports (
  export_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  manifest_digest TEXT NOT NULL,
  output_locator TEXT NOT NULL,
  created_at TEXT NOT NULL
);
