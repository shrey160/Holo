# Frontend API boundary

**Current automatic workflow (2026-10-04):** Uploads pass `automatic_reconstruction`; `reconstruct()` posts prepared runs/retries to `/jobs/{id}/reconstruct` with explicit dense or auto mode. Health reports usable CUDA. Summaries include geometry source/quality, publication IDs and skip reasons; failures retain the stopped stage. Progress distinguishes dense stereo, surfaces and room estimation. [Automatic contract](../../../AUTOMATIC_RECONSTRUCTION.md).

`client.ts` owns the shared `Job`, `Finding`, `Reference` and `Preprocessing` types plus transport helpers used by the input and review screens.

| Helper                   | Behavior                                                                                                                    |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `request<T>`             | GET a relative `/api` path, accept cancellation and surface server errors                                                   |
| `upload`                 | Send multipart files/label/reference and optional separate reference image with XMLHttpRequest progress and an abort handle |
| `preprocess`             | POST an existing capture ID and return the newly queued independent preprocessing job                                       |
| `terminal`, `stateLabel` | Identify final job states and present readable status labels                                                                |
| `downloadResult`         | Verify report availability, then let the browser stream a JSON/ZIP attachment                                               |

Uploads use XMLHttpRequest because its upload events provide actual byte progress. Capture ZIPs download through a normal browser link to avoid buffering the entire video archive in JavaScript memory. Form dimensions use centimetres; canonical annotations use metres after server validation.

Keep URLs relative. Native Vite development uses the configured proxy; compiled native/Docker mode shares the API origin. For endpoint or response changes, update these types together with the [web service](../../../src/cozmo_web/README.md) and [ingestion UI](../features/ingestion/README.md). Server validation remains authoritative.
