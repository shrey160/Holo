# Preprocessing review

`PreprocessingResult.tsx` renders selected-view counts, weak links, pose-motion findings and a paginated native-orientation thumbnail gallery. It receives typed data from the ingestion job summary; algorithms remain in [the Python package](../../../../src/cozmo_preprocessing/README.md).

The ingestion result's preparation button queues a separate run through `POST /api/jobs/{id}/preprocess`. Selecting that new history entry shows progress/results. Preview endpoints accept only selected ranks, check source-bound indices and thumbnail hashes; report/download endpoints verify the full derived bundle. LiDAR and grounding measurements are explicitly excluded. Product copy distinguishes image overlap, low baseline and unverified physical dimensions.
