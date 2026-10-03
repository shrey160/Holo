# Frontend API boundary

`client.ts` owns the shared `Job`, `Finding` and `Reference` types plus transport helpers used by the ingestion screen.

| Helper                   | Behavior                                                                                                                    |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `request<T>`             | GET a relative `/api` path, accept cancellation and surface server errors                                                   |
| `upload`                 | Send multipart files/label/reference and optional separate reference image with XMLHttpRequest progress and an abort handle |
| `terminal`, `stateLabel` | Identify final job states and present readable status labels                                                                |
| `downloadResult`         | Verify report availability, then let the browser stream a JSON/ZIP attachment                                               |

Uploads use XMLHttpRequest because its upload events provide actual byte progress. Capture ZIPs download through a normal browser link to avoid buffering the entire video archive in JavaScript memory. Form dimensions use centimetres; canonical annotations use metres after server validation.

Keep URLs relative. Native Vite development uses the configured proxy; compiled native/Docker mode shares the API origin. For endpoint or response changes, update these types together with the [web service](../../../src/cozmo_web/README.md) and [ingestion UI](../features/ingestion/README.md). Server validation remains authoritative.
