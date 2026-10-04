import { useEffect, useRef, useState } from "react";
import {
  request,
  stateLabel,
  terminal,
  upload,
  type Job,
  type PhotosReference,
  type Reference,
  type Health,
  type ReconstructionMode,
} from "../../api/client";
import { Result } from "./Result";

type Modality = "video" | "photos";

export function Input() {
  const [modality, setModality] = useState<Modality>("video");
  const [files, setFiles] = useState<File[]>([]);
  const [label, setLabel] = useState("");
  const [automatic, setAutomatic] = useState(true);
  const [denseAvailable, setDenseAvailable] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [reconstructionMode, setReconstructionMode] =
    useState<ReconstructionMode>("auto");
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
  const [photoReferenceEnabled, setPhotoReferenceEnabled] = useState(false);
  const [photosReference, setPhotosReference] = useState<PhotosReference>({
    object_id: "a4-reference-1",
    width_m: 0.21,
    height_m: 0.297,
    reference_asset: null,
    candidate_assets: [],
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
  const isPhotos = modality === "photos";
  const expectedDense =
    denseAvailable &&
    reconstructionMode !== "preview" &&
    (reconstructionMode === "dense" ||
      health?.reconstruction_mode !== "preview");
  const isZip =
    files.length === 1 && files[0].name.toLowerCase().endsWith(".zip");
  const photoNames = files.map((file) =>
    (file.webkitRelativePath || file.name).replaceAll("\\", "/"),
  );
  const isPhoto = (name: string) => /\.(jpe?g|png)$/i.test(name);
  const photoCount = photoNames.filter(isPhoto).length;
  const photoOptions = photoNames.filter(isPhoto);
  const missing = isPhotos
    ? []
    : (files.some((file) => file.name === "rgb.mp4")
        ? ["rgb.mp4", "odometry.csv", "imu.csv", "camera_matrix.csv"]
        : ["wide.mp4", "meta.json", "arkit_pose.csv"]
      ).filter((name) => !files.some((file) => file.name === name));
  const conflicts = isPhotos
    ? new Set(photoNames.map((name) => name.toLowerCase())).size !==
        photoNames.length ||
      (files.length > 1 &&
        files.some((file) => file.name.toLowerCase().endsWith(".zip")))
    : new Set(files.map((file) => file.name.toLowerCase())).size !==
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
      const health = await request<Health>("/health");
      setHealth(health);
      setReady(health.status === "ready");
      setDenseAvailable(health.dense_reconstruction);
      const list = await request<Job[]>("/jobs");
      setJobs(list);
      setSelected((id) => id || list[0]?.id || "");
    } catch (e) {
      setReady(false);
      setHealth(null);
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
  function chooseModality(next: Modality) {
    if (next === modality) return;
    setModality(next);
    setFiles([]);
    setError("");
    setImageError("");
    setReferenceImage(null);
    setProgress(null);
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setProgress(0);
    try {
      const transfer = upload(
        files,
        label,
        !isPhotos && enabled ? reference : null,
        setProgress,
        isPhotos ? null : referenceImage,
        isPhotos ? false : automatic,
        modality,
        isPhotos && photoReferenceEnabled ? photosReference : null,
        reconstructionMode,
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
  function updatePhotos<K extends keyof PhotosReference>(
    key: K,
    value: PhotosReference[K],
  ) {
    setPhotosReference((previous) => ({ ...previous, [key]: value }));
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
  const photoReferenceIncomplete =
    isPhotos &&
    photoReferenceEnabled &&
    (!photosReference.reference_asset ||
      photosReference.width_m <= 0 ||
      photosReference.height_m <= 0);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">02 / BRING YOUR CAPTURE</span>
          <h1>
            From export
            <br />
            to a rough reconstruction.
          </h1>
          <p>
            Upload room photos for validation, or an ARKit export to generate a
            rough plan and interactive 3D. Keep the original files together.
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
          <div
            className="modality-toggle"
            role="tablist"
            aria-label="Input modality"
          >
            {(["photos", "video"] as const).map((option) => (
              <button
                key={option}
                type="button"
                role="tab"
                aria-selected={modality === option}
                className={`modality ${modality === option ? "selected" : ""}`}
                disabled={progress !== null}
                onClick={() => chooseModality(option)}
              >
                {option === "photos" ? "Photos" : "Videos + intrinsics"}
              </button>
            ))}
            <span
              className="modality disabled"
              aria-disabled="true"
              title="LiDAR CLI ingestion is available; app upload is planned"
            >
              Lidar (planned)
            </span>
          </div>
          <label className="field">
            Capture name
            <input
              maxLength={120}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={
                isPhotos ? "e.g. Bedroom photos" : "e.g. Living room + hallway"
              }
            />
          </label>
          {isPhotos ? (
            <>
              <p className="caption">
                Select a room folder or its JPEG/PNG photos (or a ZIP that keeps
                per-room folders). Original files are preserved byte-for-byte.
                HEIC/HEIF must be exported to JPEG first.
              </p>
              <label className="upload-area">
                <span className="upload-icon">↑</span>
                <strong>Choose room photos</strong>
                <span>JPEG/PNG · one room folder, loose files or a ZIP</span>
                <input
                  aria-label="Choose room photos"
                  type="file"
                  multiple
                  accept=".jpg,.jpeg,.png,.zip"
                  disabled={progress !== null}
                  onChange={(e) => {
                    setFiles(Array.from(e.target.files || []));
                    setError("");
                  }}
                />
              </label>
              <label className="upload-area compact">
                <span>or choose a room folder (keeps room names)</span>
                <input
                  aria-label="Choose room folder"
                  type="file"
                  multiple
                  disabled={progress !== null}
                  onChange={(e) => {
                    setFiles(Array.from(e.target.files || []));
                    setError("");
                  }}
                  {...({ webkitdirectory: "", directory: "" } as Record<
                    string,
                    string
                  >)}
                />
              </label>
            </>
          ) : (
            <>
              <p className="caption">
                Video mode takes the original Sensor Recorder Pro ARKit export
                (camera poses, calibration and IMU) or the supplied Stray-style
                captures. For the test data, choose a ZIP from
                test_data/drive_download/zips: single_room,
                single_scan_floor_only or single_scan_with_ceiling. Depth and
                confidence files stay in the export and are excluded from
                assisted RGB processing.
              </p>
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
            </>
          )}
          {files.length > 0 && (
            <>
              <p className="selection-label">
                {isPhotos
                  ? `${photoCount} photo${photoCount === 1 ? "" : "s"} · ${files.length} file${files.length === 1 ? "" : "s"}`
                  : `${files.length} selected`}{" "}
                · {(total / 1024 ** 2).toFixed(1)} MB
              </p>
              <ul className="file-list">
                {files.map((file, index) => (
                  <li key={index}>
                    <span>{file.webkitRelativePath || file.name}</span>
                    <span>{(file.size / 1024 ** 2).toFixed(1)} MB</span>
                  </li>
                ))}
              </ul>
              {!isPhotos && !isZip && missing.length > 0 && (
                <p className="error-text">Missing: {missing.join(", ")}</p>
              )}
              {isPhotos && photoCount === 0 && (
                <p className="error-text">Choose at least one JPEG or PNG.</p>
              )}
              {conflicts && (
                <p className="error-text">
                  {isPhotos
                    ? "Choose unique photo paths without a ZIP mixed with files."
                    : "Choose one ZIP or a set of unique exported files."}
                </p>
              )}
              <p className="caption">
                {isPhotos
                  ? "Room names come from the selected folder layout. The server validates JPEG/PNG content and records EXIF; no scale is applied."
                  : "The server checks the export format and its required streams. Use ZIP for captures with depth/confidence folders."}
              </p>
            </>
          )}
          {!isPhotos && (
            <div className="runtime-card">
              <span className="eyebrow">RECONSTRUCTION READINESS</span>
              <strong>
                {!ready
                  ? "Server unavailable"
                  : !health?.automatic_reconstruction
                    ? "Reconstruction backend missing"
                    : denseAvailable
                      ? "Dense reconstruction available"
                      : "Sparse preview available"}
              </strong>
              <p>
                {!ready
                  ? "Start the native server and refresh system readiness."
                  : !health?.automatic_reconstruction
                    ? "Install the reconstruct extra to generate geometry. Input validation is available."
                    : denseAvailable
                      ? "This machine can generate dense RGB geometry, a rough room plan and a ceiling-height estimate where supported."
                      : health?.dense_unavailable_reason ||
                        "Dense reconstruction requires a CUDA backend. A sparse preview does not estimate ceiling height."}
              </p>
              {denseAvailable && (
                <small>
                  {health?.dense_backend === "colmap_executable"
                    ? "Native Windows CUDA backend"
                    : "CUDA Python backend"}
                </small>
              )}
            </div>
          )}
          {!isPhotos && (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={automatic}
                disabled={progress !== null}
                onChange={(e) => setAutomatic(e.target.checked)}
              />
              <span>
                <strong>Reconstruct automatically</strong>
                <small>
                  {expectedDense
                    ? "Verify → prepare views → dense RGB → floor, walls and ceiling → plan & 3D."
                    : "Generates a sparse preview; ceiling height is unavailable."}{" "}
                  Sensor Recorder ARKit captures; other formats are validated
                  only.
                </small>
              </span>
            </label>
          )}
          {!isPhotos && automatic && (
            <label className="field">
              Reconstruction quality
              <select
                value={reconstructionMode}
                disabled={progress !== null}
                onChange={(e) =>
                  setReconstructionMode(e.target.value as ReconstructionMode)
                }
              >
                <option value="auto">
                  Automatic —{" "}
                  {denseAvailable && health?.reconstruction_mode !== "preview"
                    ? "dense"
                    : "sparse preview"}
                </option>
                <option value="dense" disabled={!denseAvailable}>
                  Dense room reconstruction + ceiling estimate
                  {!denseAvailable ? " (unavailable)" : ""}
                </option>
                <option value="preview">Quick sparse preview</option>
              </select>
              <small>
                Dense mode stops visibly if the GPU backend fails. It preserves
                verified input for retry.
              </small>
            </label>
          )}
          {isPhotos ? (
            <div className="reference">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={photoReferenceEnabled}
                  onChange={(e) => setPhotoReferenceEnabled(e.target.checked)}
                />
                <span>
                  <strong>Declare a known-size reference</strong>
                  <small>Optional · metadata only; scale is not applied</small>
                </span>
              </label>
              {photoReferenceEnabled && (
                <>
                  <div className="reference-grid">
                    <label className="field">
                      Object ID
                      <input
                        maxLength={64}
                        value={photosReference.object_id}
                        onChange={(e) =>
                          updatePhotos("object_id", e.target.value)
                        }
                      />
                    </label>
                    <label className="field">
                      Width (m)
                      <input
                        type="number"
                        step="any"
                        min="0.001"
                        value={photosReference.width_m}
                        onChange={(e) =>
                          updatePhotos("width_m", Number(e.target.value))
                        }
                      />
                    </label>
                    <label className="field">
                      Height (m)
                      <input
                        type="number"
                        step="any"
                        min="0.001"
                        value={photosReference.height_m}
                        onChange={(e) =>
                          updatePhotos("height_m", Number(e.target.value))
                        }
                      />
                    </label>
                  </div>
                  <label className="field">
                    Reference photo
                    <select
                      value={photosReference.reference_asset || ""}
                      onChange={(e) =>
                        updatePhotos("reference_asset", e.target.value || null)
                      }
                    >
                      <option value="">Select an uploaded photo</option>
                      {photoOptions.map((name) => (
                        <option key={name} value={name.split("/").pop()}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="caption">
                    A4 preset: 0.21 × 0.297 m. Corners are not detected and
                    scale is not corrected.
                  </p>
                </>
              )}
            </div>
          ) : (
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
          )}
          <button
            className="primary submit"
            type="submit"
            disabled={
              !ready ||
              (!isPhotos &&
                automatic &&
                (reconstructionMode === "dense" ||
                  (reconstructionMode === "auto" &&
                    health?.reconstruction_mode === "dense")) &&
                !denseAvailable) ||
              (!isPhotos && automatic && !health?.automatic_reconstruction) ||
              !files.length ||
              missing.length > 0 ||
              conflicts ||
              photoReferenceIncomplete ||
              !!imageError ||
              progress !== null ||
              (!isPhotos &&
                enabled &&
                reference.end_seconds <= reference.start_seconds)
            }
          >
            {progress !== null
              ? `Uploading ${progress}%`
              : isPhotos
                ? "Validate photos →"
                : automatic
                  ? "Process & reconstruct →"
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
                <span>
                  {job.modality === "photos" ? "Photos · " : ""}
                  {stateLabel(job.state)}
                </span>
                <small>{new Date(job.created_at).toLocaleString()}</small>
              </button>
            ))
          )}
          <div className="notice">
            Videos + intrinsics: Sensor Recorder Pro 1.5 / build 5 ARKit exports
            and the supplied Stray-style captures. Photos: JPEG/PNG room sets.
            LiDAR app upload and photo reconstruction are planned.
          </div>
        </aside>
      </div>
      {current && (
        <Result
          key={current.id}
          job={current}
          denseAvailable={denseAvailable}
          onPrepared={async (id) => {
            setJobs(await request<Job[]>("/jobs"));
            setSelected(id);
          }}
        />
      )}
    </>
  );
}
