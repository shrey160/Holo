# Frontend source

| File or folder                      | Responsibility                                                            |
| ----------------------------------- | ------------------------------------------------------------------------- |
| `main.tsx`                          | Mount React and load shared CSS                                           |
| `App.tsx`                           | Holo header/footer, accessible tabs and feature lifecycle                 |
| `styles.css`                        | Shared visual styles, responsive layout and focus/reduced-motion behavior |
| `vite-env.d.ts`                     | Type declarations for Vite/raw Markdown imports                           |
| [features/](features/README.md)     | Capture guide, ingestion, preprocessing and reconstruction review         |
| [api/](api/README.md)               | Typed network boundary                                                    |
| [components/](components/README.md) | Reusable presentation components                                          |

The guide is mounted from the start. Input mounts when first visited; both panels then retain local state while tab visibility changes. Reconstruction mounts only when visited and releases GPU resources when left; the Gaussian renderer is loaded only when its scene is opened. Keep keyboard navigation, `aria-selected`, `aria-controls` and tab-panel labels aligned when changing navigation.

Product name/letter mark and accessible brand label live in `App.tsx`; the browser title lives in [index.html](../index.html). Python API presentation title lives separately in [app.py](../../src/cozmo_web/app.py). Existing internal package names are compatibility identifiers.

Run build/format commands from [frontend/](../README.md). API and workflow behavior belong in the relevant modules rather than the application shell.
