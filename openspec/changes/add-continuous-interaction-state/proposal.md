## Why

Alignment artifacts preserve individual beliefs and feedback, but they do not
derive the current requester, agent, and shared task state.  This permits a
correction to leave an unexecuted plan active and permits ordinary dialogue to
be mistaken for broad authority.

## What Changes

- Add a storage-neutral canonical interaction state and deterministic reducer.
- Track requester stance per proposition, agent assumptions and error debt,
  foreground/suspended threads, authority, supersession, and next disposition.
- Provide an `AlignmentProtocol` bridge which uses the reducer without taking
  lifecycle or completion authority.

## Non-Goals

- Cross-session YAML storage, lifecycle hooks, and Recall (#246).
- Source corroboration and contradiction adjudication (#247/#248).
- Host configuration or dispatch (#240-#243).
