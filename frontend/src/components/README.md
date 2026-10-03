# Shared UI components

`Markdown.tsx` renders guide content with ReactMarkdown and GitHub-flavoured Markdown support. Raw HTML is skipped, and links open in a separate tab with `rel="noreferrer"`. Styling comes from the shared `.markdown` rules.

Use this renderer for Markdown presentation; keep capture instructions in [capture.md](../../../capture.md). Guide-specific parsing, navigation and diagrams belong in the [guide feature](../features/guide/README.md).

Extract a component here when more than one feature needs the same presentation behavior. Keep API requests, job state and ingestion validation in their owning modules. [Frontend source map](../README.md).
