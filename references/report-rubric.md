# Report rubric

Reports are produced only from a frozen snapshot. Write for the user's stated
audience and preserve its material conditions, especially time boundaries.

## Required content

- Begin with a direct, bounded answer to the current intent version.
- Fulfil every required ready-contract deliverable. A material-analysis or
  design/experiment-plan deliverable must be a substantive chapter, not a
  generic research-summary substitute.
- Use only the research inputs bound to that deliverable's
  `research_frame_refs` / Frame `contract_ref`; unrelated frozen research is
  not an acceptable substitute for its required evidence.
- State the snapshot identifier and the effective "as of" time whenever the
  conclusion depends on time.
- Each material claim uses a readable evidence label such as `[E1]`. The
  report's evidence ledger maps that label to a frozen source title/date,
  `source_path`, and cognition locator. Keep the machine-readable `chunk_id`
  in an HTML comment or technical trace appendix rather than rendering
  `[citation: c_...]` in reader-facing prose.
- For a material/design chapter, distinguish user-material observations, cited
  external research, stated assumptions, and proposed design choices. Address
  the contracted design requirements and acceptance criteria explicitly.
- Do not describe a registered PDF, DOCX, or other non-text-extractable file as
  analyzed material unless its explicit extracted text is itself a registered,
  frozen, and cited input.
- Distinguish source facts, inferences, contradictions, and insufficient
  evidence. Do not hide conflicts to make a cleaner narrative.
- For changing claims, describe the relevant sequence and context rather than
  treating distinct conditions as a timeless contradiction.
- Include material unresolved gaps, access limitations, and deferred frames.
- Match claim strength to the chapter's source-quality and topic-confidence
  assessment. Include every required low-quality, low-confidence, or
  unassessed-evidence disclosure that applies to cited support.

## Decision-aware reports

When the frozen intent contract contains `decision_questions`, the report must
answer those questions before presenting a protocol or implementation checklist.
For every question, show the current conclusion, supporting/refuting cognition
ids through the readable evidence ledger, the inference, the action now, and
the conditions or user inputs that would change the conclusion. A conditional,
gap, user-input, or insufficient assessment cannot be rewritten as approval.

Every source accepted by the extractor has an auditable disposition. The report
may use it as a claim, context, follow-up, or explicit exclusion, but it may not
silently drop it. Every consequential parameter must carry a provenance basis
(`user_constraint`, `direct_evidence`, `transfer_method`, `assumption`, or
`need_user_input`) and the report must disclose that basis where the parameter is
used. The editor draft binds the frozen synthesis hash, question ids, and
parameter ids; a separate senior-user reviewer must approve the evidence-to-
inference-to-action chains before the editor's final compilation.

## Experiment-plan presentation

When any required deliverable is an experiment plan or material-backed design,
the compiled report is a decision document, not a short summary of writer
chapters. It must include the following sections (localized headings are fine):

- snapshot, `as of` time, evidence window, decision status, and decision owner
  or audience;
- decision summary; scoped inputs and assumptions; and an evidence-judgment
  ledger that identifies full-text, metadata-only, transferable, and direct
  support separately;
- treatment/control, execution unit, pairing or randomization, fixed
  invariants, and a run matrix;
- a metrics and adjudication table with numerator, denominator, decision time,
  missing/invalid-run handling, and owner/review rule; plus a failure taxonomy
  and replay acceptance condition;
- estimand, uncertainty method and resampling unit, pre-specified adoption and
  guardrail rules, and the outcome when a primary metric conflicts with a
  guardrail or the run stops early;
- execution schedule and budget, risk/stop/non-adoption register, limitations,
  and a readable source-and-traceability ledger.

Numerical adoption gates are proposed design choices unless supported by a
separate result. Label them as such. Preserve operational detail already
present in a submitted experiment chapter; editing may remove repetition but
must not collapse a protocol into a prose paragraph.

## Quality checks

- No live-search result, live workspace page, or uncited claim appears in the
  report.
- For an experiment-plan profile, the report includes all required presentation
  sections, snapshot/time metadata, a readable `[E1]`-style evidence ledger,
  and no visible `[citation: c_...]` prose. Compilation rejects a generic
  summary that fails this structural gate.
- Clauses marked hard in the intent are satisfied or explicitly reported as
  unresolved with their effect on the conclusion.
- Confidence reflects cited evidence quality, directness, temporal fit, and
  unresolved alternatives; it is not a count of sources or near-duplicates.
- Every claim uses only the chunks allowed by its frozen chapter contract. A
  chapter may not cite a frozen-but-not-authorized source merely because it is
  visible in the aggregation audit trail.
- For an `intent_deliverable` chapter, include every task-supplied delivery
  marker in the relevant prose, for example
  `<!-- research-tree:check design-1 -->`. The marker records deliberate
  coverage; it does not replace the prose or the editor's semantic review.
- Each required material or bound research input with citable chunks must be
  represented by at least one permitted frozen chunk citation. When a required
  input has no citable chunk, retain its checklist marker and state the
  limitation rather than inventing a citation.
- The editor verifies the chapter evidence-assessment hash, required
  disclosures, and delivery contract before compilation. Missing limitations,
  unsupported confidence, or unmet material/design acceptance criteria produce
  a repair task rather than a silently weakened or invented report section.
- A missing delivery marker or required-input citation rejects chapter
  submission and blocks report compilation. Separately, a required research
  deliverable without a bound terminal Frame containing cited cognition blocks
  freeze, so writing cannot paper over a missing research stage.
- The report uses the default Markdown output. PDF conversion occurs only after
  an explicit user request.

## Frozen Q&A

Question answering starts only after a validated frozen snapshot exists. It
must use the snapshot's allowed chunks and cite `chunk_id` plus `source_path`.
It returns `partial` or `unknown` when the snapshot is insufficient; it must
not initiate new research, reinterpret the live DAG, or silently use live
materials.
