export type Finding = { code: string; details: unknown };
export type Job = {
  id: string;
  label: string;
  state: string;
  created_at: string;
  error: { code: string; message: string } | null;
  reference_image?: null | {
    original_name: string;
    width: number;
    height: number;
    sha256: string;
  };
  summary: null | {
    frame_count: number;
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
  };
};
export type Reference = {
  width_cm: number;
  height_cm: number;
  start_seconds: number;
  end_seconds: number;
  placement: string;
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
    SUCCEEDED: "Verified with findings",
    FAILED: "Needs attention",
  })[state] || state;

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
): { promise: Promise<{ id: string }>; cancel: () => void } {
  const xhr = new XMLHttpRequest();
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("label", label);
  if (reference) form.append("reference", JSON.stringify(reference));
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
