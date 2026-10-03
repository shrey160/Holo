# Capture guide feature

`Guide.tsx` imports [capture.md](../../../../capture.md) as raw text, extracts its sections and numbered walkthrough, and presents preparation notes, device settings, step cards, handoff instructions and deferred grounding guidance. A small SVG diagram highlights the route for the selected step.

The guide is available without API requests. It documents the iPhone/Sensor Recorder Pro setup (iPhone 15 and above recommended), a reference-first opening and continuous clockwise room coverage.

## Editing the protocol

Edit `capture.md` first. The parser uses exact level-two section names, a numbered walkthrough, and bold text at the start of each step for card titles. If those structures change, update the parser at the same time. The current heading keys are visible at the top of `Guide.tsx` and its section accesses.

Protocol text is bundled at build time. Vite development reflects source edits; compiled native and Docker deployments need a new frontend build. Use the shared [Markdown renderer](../../components/README.md) rather than inserting raw HTML.

After a guide change, check every step, next/previous controls, settings table and mobile layout. The diagram is instructional; it is not a reconstructed floor plan. [Frontend setup](../../../README.md).
