# Input and validation feature

| File         | Responsibility                                                                                                          |
| ------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `Input.tsx`  | Health check, ZIP/multi-file selection, capture label/reference form, upload progress, job polling/history and failures |
| `Result.tsx` | Verified frame/artifact counts, stream/tracking availability, readable findings and result downloads                    |

Select one complete export ZIP or the files from one session together. The frontend gives early selection feedback; the [server](../../../../src/cozmo_web/README.md) validates format, paths, stream requirements, resource limits and source integrity. Selecting only an MP4 cannot satisfy the supported assisted-iOS contract.

The optional photo picker previews one JPEG/PNG image, supports removal and uploads it separately from the export (10 MiB maximum). It can be used without entering dimensions. Verified results show the persisted image; portable downloads include the original photo and its video/hash-bound metadata.

The optional known-size reference defaults to the supplied 21 × 29.7 cm A4 dimensions and a 0–5 second candidate window when enabled. These are declarations, not detected corners or measurement corrections. New captures bind their metadata to their own video hash.

Upload progress describes transferred bytes. Subsequent job state describes server processing; successful upload is not completed verification. Active history polls for updates, terminal jobs stop active polling, and selecting history displays persisted results. A failed job can be resubmitted as a fresh capture.

Use [client.ts](../../api/README.md) for transport and shared response types. Keep quality findings readable while preserving their exact codes/details for inspection. Results must continue to distinguish ingestion verification from unverified metric accuracy and future geometry stages.

After a workflow change, check successful/failed uploads, server unavailable/queue-full states, reference validation, tab-state preservation, history selection and both downloads. [Frontend setup](../../../README.md) · [Observed verification](../../../../WEB_RESULTS.md).
