import { useEffect, useRef, useState } from "react";
import {
  request,
  stateLabel,
  terminal,
  upload,
  type Job,
  type Reference,
} from "../../api/client";
import { Result } from "./Result";

export function Input() {
  const [files, setFiles] = useState<File[]>([]);
  const [label, setLabel] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [referenceImage, setReferenceImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState("");
  const [imageError, setImageError] = useState("");
  const imageInput = useRef<HTMLInputElement | null>(null);
  const [reference, setReference] = useState<Reference>({
    width_cm: 21,
    height_cm: 29.7,
    start_seconds: 0,
    end_seconds: 5,
    placement: "on the ground at the opening",
  });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const cancelUpload = useRef<(() => void) | null>(null);
  const current = jobs.find((job) => job.id === selected);
  const active = jobs.some((job) => !terminal(job));
  const total = files.reduce((sum, file) => sum + file.size, 0);
  const isZip =
    files.length === 1 && files[0].name.toLowerCase().endsWith(".zip");
  const missing = isZip
    ? []
    : ["wide.mp4", "meta.json", "arkit_pose.csv"].filter(
        (name) => !files.some((file) => file.name === name),
      );
  const conflicts =
    new Set(files.map((file) => file.name.toLowerCase())).size !==
      files.length ||
    (files.length > 1 &&
      files.some((file) => file.name.toLowerCase().endsWith(".zip")));
  useEffect(() => {
    if (!referenceImage) {
      setImagePreview("");
      return;
    }
    const url = URL.createObjectURL(referenceImage);
    setImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [referenceImage]);
  async function refresh() {
    setError("");
    try {
      const health = await request<{ status: string }>("/health");
      setReady(health.status === "ready");
      const list = await request<Job[]>("/jobs");
      setJobs(list);
      setSelected((id) => id || list[0]?.id || "");
    } catch (e) {
      setReady(false);
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void refresh();
    return () => {
      cancelUpload.current?.();
    };
  }, []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = setInterval(() => {
      request<Job[]>("/jobs", controller.signal)
        .then(setJobs)
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    }, 1000);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [active]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setProgress(0);
    try {
      const transfer = upload(
        files,
        label,
        enabled ? reference : null,
        setProgress,
        referenceImage,
      );
      cancelUpload.current = transfer.cancel;
      const result = await transfer.promise;
      const list = await request<Job[]>("/jobs");
      setJobs(list);
      setSelected(result.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setProgress(null);
      cancelUpload.current = null;
    }
  }
  function update(key: keyof Reference, value: string) {
    setReference((previous) => ({
      ...previous,
      [key]: key === "placement" ? value : Number(value),
    }));
  }
  function chooseImage(file: File | undefined) {
    setImageError("");
    if (
      file &&
      (!/\.(jpe?g|png)$/i.test(file.name) ||
        !file.size ||
        file.size > 10 * 1024 ** 2)
    ) {
      setReferenceImage(null);
      setImageError("Choose a JPEG or PNG photo, up to 10 MiB.");
      return;
    }
    setReferenceImage(file || null);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">02 / BRING YOUR CAPTURE</span>
          <h1>
            From export
            <br />
            to verified input.
          </h1>
          <p>
            Upload a complete Sensor Recorder session. Keep the original video
            and sidecars together.
          </p>
        </div>
        <button
          className={`pill health ${ready ? "ready" : ""}`}
          onClick={refresh}
        >
          {ready ? "● System ready" : "○ Check system"}
        </button>
      </div>
      <div className="input-grid">
        <form className="panel section" onSubmit={submit}>
          <h2>New capture</h2>
          <label className="field">
            Capture name
            <input
              maxLength={120}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Living room + hallway"
            />
          </label>
          <label className="upload-area">
            <span className="upload-icon">↑</span>
            <strong>Choose an export ZIP or its files</strong>
            <span>One complete session · Original files only</span>
            <input
              aria-label="Choose capture export"
              type="file"
              multiple
              accept=".zip,.mp4,.csv,.json"
              disabled={progress !== null}
              onChange={(e) => {
                setFiles(Array.from(e.target.files || []));
                setError("");
              }}
            />
          </label>
          {files.length > 0 && (
            <>
              <p className="selection-label">
                {files.length} selected · {(total / 1024 ** 2).toFixed(1)} MB
              </p>
              <ul className="file-list">
                {files.map((file, index) => (
                  <li key={index}>
                    <span>{file.name}</span>
                    <span>{(file.size / 1024 ** 2).toFixed(1)} MB</span>
                  </li>
                ))}
              </ul>
              {!isZip && missing.length > 0 && (
                <p className="error-text">Missing: {missing.join(", ")}</p>
              )}
              {conflicts && (
                <p className="error-text">
                  Choose one ZIP or a set of unique exported files.
                </p>
              )}
              <p className="caption">
                The server also checks every stream enabled in your export
                metadata.
              </p>
            </>
          )}
          <div className="reference">
            <label className="field">
              Grounding object photo (optional)
              <input
                ref={imageInput}
                type="file"
                accept="image/jpeg,image/png,.jpg,.jpeg,.png"
                disabled={progress !== null}
                onChange={(e) => chooseImage(e.target.files?.[0])}
              />
            </label>
            <p className="caption">
              Attach a clear photo of the one object shown in the first 3–5
              seconds. JPEG or PNG, up to 10 MiB. It is saved for a later
              grounding check.
            </p>
            {imageError && (
              <p role="alert" className="error-text">
                {imageError}
              </p>
            )}
            {referenceImage && (
              <div className="reference-photo">
                {imagePreview && (
                  <img src={imagePreview} alt="Selected grounding object" />
                )}
                <span>{referenceImage.name}</span>
                <button
                  type="button"
                  className="text-button"
                  disabled={progress !== null}
                  onClick={() => {
                    setReferenceImage(null);
                    setImageError("");
                    if (imageInput.current) imageInput.current.value = "";
                  }}
                >
                  Remove photo
                </button>
              </div>
            )}
            <label className="checkbox">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              <span>
                <strong>Declare a known-size reference</strong>
                <small>Optional · Metadata for a later grounding check</small>
              </span>
            </label>
            {enabled && (
              <>
                <div className="reference-grid">
                  {(
                    [
                      ["width_cm", "Width (cm)"],
                      ["height_cm", "Height (cm)"],
                      ["start_seconds", "Start (seconds)"],
                      ["end_seconds", "End (seconds)"],
                    ] as const
                  ).map(([key, text]) => (
                    <label className="field" key={key}>
                      {text}
                      <input
                        type="number"
                        required
                        step="any"
                        min={key === "start_seconds" ? 0 : 0.001}
                        value={reference[key]}
                        onChange={(e) => update(key, e.target.value)}
                      />
                    </label>
                  ))}
                </div>
                <label className="field">
                  Placement
                  <input
                    maxLength={300}
                    value={reference.placement}
                    onChange={(e) => update("placement", e.target.value)}
                  />
                </label>
                <p className="caption">
                  A4 preset: 21 × 29.7 cm. Confirm the actual object size.
                  Declaring it does not detect corners or correct scale.
                </p>
              </>
            )}
          </div>
          <button
            className="primary submit"
            type="submit"
            disabled={
              !ready ||
              !files.length ||
              missing.length > 0 ||
              conflicts ||
              !!imageError ||
              progress !== null ||
              (enabled && reference.end_seconds <= reference.start_seconds)
            }
          >
            {progress !== null
              ? `Uploading ${progress}%`
              : "Validate capture →"}
          </button>
          {progress !== null && (
            <progress value={progress} max={100} aria-label="Upload progress" />
          )}
          {error && (
            <p role="alert" className="error-text">
              {error}
            </p>
          )}
        </form>
        <aside className="panel section history">
          <div className="result-header">
            <h2>Recent captures</h2>
            <button className="text-button" onClick={refresh}>
              Refresh
            </button>
          </div>
          {jobs.length === 0 ? (
            <div className="empty">
              <span>◎</span>
              <h3>Your first capture starts here.</h3>
              <p>Verified results and any findings will appear here.</p>
            </div>
          ) : (
            jobs.map((job) => (
              <button
                key={job.id}
                className={`job ${selected === job.id ? "selected" : ""}`}
                onClick={() => setSelected(job.id)}
              >
                <strong>{job.label}</strong>
                <span>{stateLabel(job.state)}</span>
                <small>{new Date(job.created_at).toLocaleString()}</small>
              </button>
            ))
          )}
          <div className="notice">
            Supported now: Sensor Recorder Pro 1.5 / build 5, ARKit exports.
            Android and other capture formats will be added separately.
          </div>
        </aside>
      </div>
      {current && <Result key={current.id} job={current} />}
    </>
  );
}
