## ADDED Requirements

### Requirement: direct fetch converts HTML to markdown with the title preserved

#### Scenario: article extraction
- **WHEN** an HTML page is fetched
- **THEN** the document is markdown containing the article title and section content, contentType text/markdown

### Requirement: plain text and code are preserved with deterministic summaries

Summaries are mechanical (title/outline/code inventory/line+byte counts) — no LLM calls in the provider layer.

#### Scenario: plain text summary
- **WHEN** a text/plain resource is fetched
- **THEN** the raw text is preserved and the summary carries the outline and line/byte counts

#### Scenario: code summary with language detection
- **WHEN** a code resource is fetched
- **THEN** the summary inventories code blocks with detected language

### Requirement: office and pdf documents convert through markitdown

pdf/pptx/docx/xlsx downloads run through the markitdown CLI (MIT, local).

#### Scenario: pdf conversion
- **WHEN** a pdf is fetched
- **THEN** the download runs through markitdown and the markdown output becomes the document

#### Scenario: conversion failure is structured
- **WHEN** markitdown exits non-zero
- **THEN** fetch raises a structured markitdown failure

### Requirement: failure semantics and caps

HTTP errors, oversize downloads, and CLI failures are structured; no silent empty evidence.

#### Scenario: HTTP error
- **WHEN** the response status is not ok
- **THEN** fetch raises naming the status

#### Scenario: size cap
- **WHEN** a download exceeds the configured cap
- **THEN** fetch raises naming the size cap
