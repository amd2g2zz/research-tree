## 1. Contract And Governance

- [x] 1.1 Register issue #174 / group 60 with the strict Insight Digest
  reader acceptance command and a rollback that does not restore compatibility.
- [x] 1.2 Align active Insight Digest requirements, schema, and example with
  the complete current writer payload.

## 2. Focused Regressions

- [x] 2.1 Add failing tests proving a canonical rich writer payload validates
  at the runtime and scheduler boundaries.
- [x] 2.2 Add failing tests proving the former minimal and every
  missing-current-field payload reject before policy, replay, or delivery use.

## 3. Strict Reader Removal

- [x] 3.1 Delete the missing-version legacy return and require the complete
  current payload at Insight Digest validation.
- [x] 3.2 Remove active contract language and schema/example definitions that
  advertise a minimal reader contract without touching user data.

## 4. Verification And Handoff

- [x] 4.1 Run the group-60 focused acceptance command, strict OpenSpec
  validation, governance validation, and relevant regression checks.
- [x] 4.2 Commit source changes before a later source-bound group-60 receipt;
  do not edit #171 or #168 shared evidence surfaces.
