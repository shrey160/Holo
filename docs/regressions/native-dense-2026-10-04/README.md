# Frozen native dense error baseline

This directory holds a small, reviewable snapshot of the native run `ae77c443f85f449abad2c0598d4c7648` on 2026-10-04. Its pipeline completed with dense RGB geometry and a provisional 2.551 m ceiling, but its 4.539 × 4.055 m inferred plan is wider than the earlier automatic estimate.

`evidence.json` records the exact source/result identity, output measurements, backend provenance, validation limits and artifact hashes. `rough-room.svg` is an unchanged copy of the published plan. Raw data and large generated artifacts remain in ignored local outputs; they are not embedded in Git.

Preserve these files as the pre-fix baseline. Store future corrected results separately, with their own source bindings and assumptions. [Issue, reproduction and next investigation](../../../NATIVE_DENSE_REGRESSION.md).
