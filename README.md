# EKPS Clean Chunker

A data-processing tool for Dify **knowledge pipelines** (Dify 1.9.0+), built for Chinese policy and regulation documents.

Put it after an extractor (e.g. Dify Extractor). Two tools are included:

- **Clean & Chunk by Clause**: connect its `result` to a **General**-mode Knowledge Base node.
- **Clean & Chunk by Clause (Parent-Child)**: each clause becomes a parent chunk and each sentence a child chunk (table rows become children with the header row repeated); connect its `result` to a **Parent-child**-mode Knowledge Base node.

Tested on Dify Cloud with a knowledge pipeline (File → Dify Extractor → this tool → Knowledge Base).

## What it does (one document at a time)

1. **Removes noise**: cover and sign-off lines (organization name, document number, date on their own line), separator lines, page numbers, table-of-contents lines, addressee lines, and the title line. Lines containing amounts, deadlines or prohibitions ("must not", "prohibited"...) are always kept.
2. **Chunks by clause**: a new chunk starts at each clause marker ("Article N" in Chinese numbering); following paragraphs stay with their clause. Chapter headings ("Chapter N", Markdown headings) go into the context header instead of becoming chunks. A Markdown table stays in one chunk together with its caption; long tables are split by rows with the header row repeated. Without clause numbers, each paragraph is its own chunk.
3. **Adds a context header** to every chunk: `【《title》｜document number｜effective date｜chapter】`, so a single retrieved chunk still tells which document and version it comes from.

## Setup

1. Install the plugin from the Dify Marketplace (requires Dify 1.9.0 or later). No credentials or API keys are needed.
2. In a knowledge pipeline, add **Clean & Chunk by Clause** (or the Parent-Child version) after the extractor.
3. Set **Input Content** to the extractor's text output, and set the Knowledge Base node's chunk input to this tool's `result`.
4. Use **Test Run** to preview the chunks before publishing the pipeline.

## Parameters

| Name | Required | Description |
| --- | --- | --- |
| `input_text` | yes | Text of one document |
| `title` | no | Document title; if empty, the first title-like line is used |
| `max_length` | no | Maximum characters per chunk, including the context header and table caption (default 500) |
| `context_header` | no | Add the context header (default on) |

## What it does NOT do

It sees one document at a time, so it cannot retire superseded versions, remove duplicates across files, or detect conflicts between documents. For whole-library checks and cleaning, see the EKPS local tools.

## Privacy

No network requests, no credentials, no data stored. See [PRIVACY.md](PRIVACY.md).

## Source code

https://github.com/Cylunjoe/ekps-clean-chunker

Simplified Chinese documentation: [readme/README_zh_Hans.md](readme/README_zh_Hans.md).
