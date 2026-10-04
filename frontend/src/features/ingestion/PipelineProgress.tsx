import { stateLabel, type Job } from "../../api/client";

const groups = [
  { label: "Validate input", states: ["VALIDATING_INPUT", "INGESTING"] },
  { label: "Prepare views", states: ["PREPROCESSING"] },
  {
    label: "Reconstruct",
    states: [
      "RECONSTRUCTING",
      "DENSE_RECONSTRUCTING",
      "EXTRACTING_SURFACES",
      "ESTIMATING_ROOM",
    ],
  },
  { label: "Publish plan & 3D", states: ["PUBLISHING"] },
];

export function PipelineProgress({ job }: { job: Job }) {
  const stages =
    job.modality === "photos"
      ? [
          {
            label: "Validate photos",
            states: ["VALIDATING_INPUT", "INGESTING"],
          },
          { label: "Verify & save", states: ["VERIFYING"] },
        ]
      : groups;
  const visited = new Set((job.stage_history || []).map((s) => s.stage));
  const current = stages.findIndex((g) => g.states.includes(job.state));
  const reached = Math.max(
    current,
    ...stages.map((g, i) => (g.states.some((s) => visited.has(s)) ? i : -1)),
  );
  return (
    <div className="pipeline-progress" role="status">
      <strong>{stateLabel(job.state)}</strong>
      <p>
        {job.state === "DENSE_RECONSTRUCTING"
          ? "Dense stereo is running on the GPU. This stage can take several minutes."
          : "This run updates automatically as each stage completes."}
      </p>
      <ol>
        {stages.map((g, i) => (
          <li
            key={g.label}
            className={
              i < reached ? "done" : i === reached ? "current" : "pending"
            }
            aria-current={i === reached ? "step" : undefined}
          >
            {i < reached ? "✓ " : ""}
            {g.label}
          </li>
        ))}
      </ol>
    </div>
  );
}
