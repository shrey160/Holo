export type Finding = { code: string; details: unknown };
export type ReconstructionMode = "auto" | "dense" | "preview";
export type Health = {
  status: string;
  automatic_reconstruction: boolean;
  dense_reconstruction: boolean;
  dense_backend?: string | null;
  dense_unavailable_reason?: string | null;
  reconstruction_mode: ReconstructionMode;
};
export type Preprocessing = {
  source_frame_count: number;
  candidate_count: number;
  selected_count: number;
  supported_links: number;
  weak_links: {
    first_rank: number;
    second_rank: number;
    time_gap_seconds: number;
  }[];
  temporal_components: number;
  low_baseline_links: number;
  maximum_selected_gap_seconds: number;
  readiness: string;
  pose_speed_events: { seconds: number; speed_m_s: number }[];
  previews: { rank: number; seconds: number; score: number; flags: string[] }[];
};
export type Job = {
  id: string;
  label: string;
  state: string;
  modality?: string;
  created_at: string;
  stage_history?: { stage: string; started_at: string }[];
  failed_stage?: string;
  error: { code: string; message: string } | null;
  reference_image?: null | {
    original_name: string;
    width: number;
    height: number;
    sha256: string;
  };
  summary: null | {
    modality?: string;
    frame_count: number;
    room_count?: number;
    image_count?: number;
    distinct_image_count?: number;
    profile?: string;
    capabilities: Record<string, string>;
    tracking_states: Record<string, number>;
    findings: Finding[];
    grounding: string;
    independent_accuracy: string;
    verification: {
      status: string;
      source_values_preserved: boolean;
      artifacts_verified: number;
    };
    reconstruction?: {
      id: string;
      point_count: number;
      selected_views: number;
      status: string;
      geometry_source?: string;
      quality?: string;
      dimensions_estimated_m?: number[];
      ceiling_estimated_m?: number | null;
    } | null;
    automatic_reconstruction?: { status: string; reason?: string } | null;
    preprocessing?: Preprocessing | null;
  };
};
export type Reference = {
  width_cm: number;
  height_cm: number;
  start_seconds: number;
  end_seconds: number;
  placement: string;
};
export type PhotosReference = {
  object_id: string;
  width_m: number;
  height_m: number;
  reference_asset: string | null;
  candidate_assets: string[];
};
export const terminal = (job: Job) =>
  ["SUCCEEDED", "FAILED"].includes(job.state);
export const stateLabel = (state: string) =>
  ({
    RECEIVING: "Receiving files",
    QUEUED: "Queued",
    VALIDATING_INPUT: "Checking export",
    INGESTING: "Validating capture",
    VERIFYING: "Verifying source values",
    PREPROCESSING: "Preparing reconstruction views",
    RECONSTRUCTING: "Reconstructing RGB geometry",
    DENSE_RECONSTRUCTING: "Reconstructing dense RGB stereo",
    EXTRACTING_SURFACES: "Finding supported surfaces",
    ESTIMATING_ROOM: "Estimating floor, walls and ceiling",
    PUBLISHING: "Publishing plan and 3D view",
    SUCCEEDED: "Processing complete",
    FAILED: "Needs attention",
  })[state] || state;

export async function preprocess(jobId: string): Promise<{ id: string }> {
  const response = await fetch(`/api/jobs/${jobId}/preprocess`, {
    method: "POST",
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error?.message || "Preprocessing could not start.");
  return result;
}

export async function request<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api${path}`, { signal });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.error?.message ||
        data.message ||
        "The API could not complete this request.",
    );
  return data;
}

export function upload(
  files: File[],
  label: string,
  reference: Reference | null,
  onProgress: (percent: number) => void,
  referenceImage: File | null = null,
  automaticReconstruction = true,
  modality = "video",
  photosReference: PhotosReference | null = null,
  reconstructionMode: ReconstructionMode = "auto",
): { promise: Promise<{ id: string }>; cancel: () => void } {
  const xhr = new XMLHttpRequest();
  const form = new FormData();
  files.forEach((file) =>
    form.append("files", file, file.webkitRelativePath || file.name),
  );
  form.append("label", label);
  form.append("modality", modality);
  form.append("automatic_reconstruction", String(automaticReconstruction));
  form.append("reconstruction_mode", reconstructionMode);
  if (photosReference)
    form.append("reference", JSON.stringify(photosReference));
  else if (reference) form.append("reference", JSON.stringify(reference));
  if (referenceImage) form.append("reference_image", referenceImage);
  const promise = new Promise<{ id: string }>((resolve, reject) => {
    xhr.open("POST", "/api/jobs");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => {
      try {
        const result = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(result);
        else
          reject(
            new Error(
              result.error?.message ||
                "Upload was rejected. Check the complete export.",
            ),
          );
      } catch {
        reject(
          new Error(
            "Unexpected server response. Confirm that the API is running.",
          ),
        );
      }
    };
    xhr.onerror = () =>
      reject(
        new Error("Cannot reach the API. Start the server and try again."),
      );
    xhr.onabort = () => reject(new Error("Upload cancelled."));
    xhr.send(form);
  });
  return { promise, cancel: () => xhr.abort() };
}

export async function downloadResult(
  jobId: string,
  kind: "report" | "download",
) {
  // Verify first, then let the browser stream the attachment instead of buffering a video ZIP.
  const response = await fetch(`/api/jobs/${jobId}/report`);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error?.message || "Download failed.");
  }
  await response.json();
  const anchor = document.createElement("a");
  anchor.href = `/api/jobs/${jobId}/${kind}`;
  anchor.download =
    kind === "report"
      ? "validation-report.json"
      : `capture-${jobId.slice(0, 8)}.zip`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

export async function reconstruct(
  jobId: string,
  dense = false,
): Promise<{ id: string }> {
  const form = new FormData();
  form.append("reconstruction_mode", dense ? "dense" : "auto");
  const response = await fetch(`/api/jobs/${jobId}/reconstruct`, {
    method: "POST",
    body: form,
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error?.message || "Reconstruction could not start.");
  return result;
}
