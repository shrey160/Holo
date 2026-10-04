import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { Scene } from "./types";

export function PointCloudViewer({
  scene: data,
  base,
}: {
  scene: Scene;
  base: string;
}) {
  const host = useRef<HTMLDivElement>(null),
    view = useRef<(mode: string) => void>(() => {}),
    settings = useRef({
      size: 0.025,
      path: true,
      evidence: true,
      objects: true,
      height: 4,
    });
  const [size, setSize] = useState(0.025),
    [path, setPath] = useState(true),
    [evidence, setEvidence] = useState(true),
    [objects, setObjects] = useState(true),
    [height, setHeight] = useState(4),
    [status, setStatus] = useState("Loading audited point cloud…"),
    [failure, setFailure] = useState("");
  useEffect(() => {
    settings.current = { size, path, evidence, objects, height };
  }, [size, path, evidence, objects, height]);
  useEffect(() => {
    const controller = new AbortController();
    let disposed = false,
      cleanup = () => {};
    setFailure("");
    setStatus("Loading audited point cloud…");
    async function load() {
      const buffers = await Promise.all(
        ["positions.bin", "colors.bin"].map(async (asset) => {
          const response = await fetch(`${base}/${asset}`, {
            signal: controller.signal,
          });
          if (!response.ok)
            throw new Error(`Point cloud unavailable (${response.status}).`);
          return response.arrayBuffer();
        }),
      );
      if (disposed || !host.current) return;
      if (
        buffers[0].byteLength !== data.point_count * 12 ||
        buffers[1].byteLength !== data.point_count * 3
      )
        throw new Error("Point-cloud layout mismatch.");
      const scene = new THREE.Scene();
      scene.background = new THREE.Color("#edf1ec");
      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      const camera = new THREE.PerspectiveCamera(45, 1, 0.02, 200),
        controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      renderer.domElement.tabIndex = 0;
      renderer.domElement.setAttribute(
        "aria-label",
        "Interactive reconstructed room point cloud. Drag to orbit, right drag to pan, wheel to zoom.",
      );
      controls.listenToKeyEvents(renderer.domElement);
      host.current.replaceChildren(renderer.domElement);
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(new Float32Array(buffers[0]), 3),
      );
      const rgb = new Uint8Array(buffers[1]),
        colors = new Float32Array(rgb.length),
        color = new THREE.Color();
      for (let i = 0; i < rgb.length; i += 3) {
        color.setRGB(
          rgb[i] / 255,
          rgb[i + 1] / 255,
          rgb[i + 2] / 255,
          THREE.SRGBColorSpace,
        );
        colors.set([color.r, color.g, color.b], i);
      }
      geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      const material = new THREE.PointsMaterial({
        vertexColors: true,
        size: 0.025,
        sizeAttenuation: true,
      });
      scene.add(new THREE.Points(geometry, material));
      const pathGeometry = new THREE.BufferGeometry().setFromPoints(
          data.camera_path.map(
            (p) => new THREE.Vector3(...(p as [number, number, number])),
          ),
        ),
        pathMaterial = new THREE.LineBasicMaterial({ color: 0x725696 }),
        route = new THREE.Line(pathGeometry, pathMaterial);
      scene.add(route);
      const evidenceGroup = new THREE.Group();
      scene.add(evidenceGroup);
      const geometries: THREE.BufferGeometry[] = [],
        materials: THREE.Material[] = [];
      const objectGroup = new THREE.Group();
      scene.add(objectGroup);
      for (const obj of data.approximate_objects || []) {
        if (!obj.footprint_floor_uv_m) continue;
        const g = new THREE.BufferGeometry().setFromPoints(
          obj.footprint_floor_uv_m.map(
            (p) => new THREE.Vector3(p[0], 0.035, -p[1]),
          ),
        );
        const m = new THREE.LineBasicMaterial({
          color: obj.color || "#a67530",
        });
        geometries.push(g);
        materials.push(m);
        objectGroup.add(new THREE.Line(g, m));
      }
      for (const s of data.reviewed_spans) {
        const [a, b] = s.endpoints_floor_uv_m,
          g = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(a[0], 0.015, -a[1]),
            new THREE.Vector3(b[0], 0.015, -b[1]),
          ]),
          m = new THREE.LineBasicMaterial({ color: 0x1675b6 });
        geometries.push(g);
        materials.push(m);
        evidenceGroup.add(new THREE.Line(g, m));
      }
      const floorMaterial = new THREE.MeshBasicMaterial({
        color: 0x2d9d78,
        transparent: true,
        opacity: 0.35,
        side: THREE.DoubleSide,
      });
      materials.push(floorMaterial);
      for (const { cell } of data.floor_cells) {
        const g = new THREE.PlaneGeometry(data.cell_m, data.cell_m);
        geometries.push(g);
        const mesh = new THREE.Mesh(g, floorMaterial);
        mesh.rotation.x = -Math.PI / 2;
        mesh.position.set(
          (cell[0] + 0.5) * data.cell_m,
          0,
          -(cell[1] + 0.5) * data.cell_m,
        );
        evidenceGroup.add(mesh);
      }
      // Frame the inferred room, while retaining every displayed source point.
      // Isolated stereo points below/outside the room must not shrink the initial view.
      const room = data.inferred_room_completion;
      const polygon = room?.polygon_floor_uv_m;
      const roomBounds =
        polygon?.length &&
        polygon.every((p) => p.length === 2 && p.every(Number.isFinite))
          ? new THREE.Box3().setFromPoints(
              polygon.flatMap((p) => [
                new THREE.Vector3(p[0], 0, -p[1]),
                new THREE.Vector3(
                  p[0],
                  room?.ceiling_estimate?.height_estimated_m ?? 3,
                  -p[1],
                ),
              ]),
            )
          : null;
      const low =
          roomBounds?.min ??
          new THREE.Vector3(...(data.bounds[0] as [number, number, number])),
        high =
          roomBounds?.max ??
          new THREE.Vector3(...(data.bounds[1] as [number, number, number])),
        center = low.clone().add(high).multiplyScalar(0.5),
        extent = Math.max(high.x - low.x, high.y - low.y, high.z - low.z, 1);
      const grid = new THREE.GridHelper(
        Math.ceil(extent + 2),
        Math.ceil(extent + 2),
        0x8ba79b,
        0xc8d6cd,
      );
      scene.add(grid);
      const reset = (mode: string) => {
        controls.target.copy(center);
        camera.up.set(0, 1, 0);
        if (mode === "top") {
          const axes = data.inferred_room_completion?.axes_in_floor_uv;
          camera.up.set(axes?.[1][0] || 0, 0, -(axes?.[1][1] ?? 1));
          camera.position.set(
            center.x,
            center.y + extent * 1.7,
            center.z + 0.001,
          );
        } else if (mode === "front")
          camera.position.set(
            center.x,
            center.y + extent * 0.15,
            center.z + extent * 1.8,
          );
        else
          camera.position
            .copy(center)
            .add(
              new THREE.Vector3(extent * 1.05, extent * 0.85, extent * 1.05),
            );
        camera.lookAt(center);
        controls.update();
      };
      view.current = reset;
      reset("orbit");
      const resize = new ResizeObserver(() => {
        if (!host.current) return;
        const w = host.current.clientWidth,
          h = host.current.clientHeight;
        if (!w || !h) return;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      });
      resize.observe(host.current);
      const clipping = new THREE.Plane(new THREE.Vector3(0, -1, 0), 4);
      let frame = 0;
      const animate = () => {
        const s = settings.current;
        material.size = s.size;
        route.visible = s.path;
        evidenceGroup.visible = s.evidence;
        objectGroup.visible = s.objects;
        clipping.constant = s.height;
        renderer.clippingPlanes = [clipping];
        controls.update();
        renderer.render(scene, camera);
        frame = requestAnimationFrame(animate);
      };
      animate();
      setStatus(
        `${data.point_count.toLocaleString()} displayed points · ${data.source_voxel_points.toLocaleString()} source ${data.geometry_source === "CPU_SPARSE_TRIANGULATION" ? "points" : "voxels"}`,
      );
      cleanup = () => {
        cancelAnimationFrame(frame);
        resize.disconnect();
        controls.dispose();
        geometry.dispose();
        material.dispose();
        pathGeometry.dispose();
        pathMaterial.dispose();
        grid.geometry.dispose();
        (grid.material as THREE.Material).dispose();
        geometries.forEach((g) => g.dispose());
        materials.forEach((m) => m.dispose());
        renderer.dispose();
        renderer.domElement.remove();
        view.current = () => {};
      };
    }
    load().catch((error) => {
      if (!disposed && error.name !== "AbortError") {
        setFailure(
          error.message || "WebGL unavailable. Use the plan or PLY download.",
        );
        setStatus("3D viewer unavailable");
      }
    });
    return () => {
      disposed = true;
      controller.abort();
      cleanup();
    };
  }, [base, data]);
  return (
    <section className="reconstruction-view panel">
      <div className="reconstruction-view-heading">
        <div>
          <p className="eyebrow">02 / SPATIAL VIEW</p>
          <h2>Interactive 3D reconstruction</h2>
        </div>
        <a href={`${base}/cloud.ply`} download>
          Download PLY
        </a>
      </div>
      <p className="muted">
        Drag to orbit · right-drag / two fingers to pan · scroll or pinch to
        zoom.{" "}
        {data.geometry_source === "CPU_SPARSE_TRIANGULATION"
          ? "Colour points are sparse triangulated RGB features; coverage has gaps."
          : "Colour points come from RGB stereo; observed geometry retains gaps."}
      </p>
      <div className="viewer-controls">
        <button onClick={() => view.current("orbit")}>Reset view</button>
        <button onClick={() => view.current("top")}>Top</button>
        <button onClick={() => view.current("front")}>Front</button>
        {data.inferred_room_completion?.ceiling_estimate?.height_estimated_m !=
          null && (
          <button
            onClick={() =>
              setHeight(
                Math.round(
                  data.inferred_room_completion!.ceiling_estimate!
                    .height_estimated_m! * 10,
                ) / 10,
              )
            }
          >
            Estimated ceiling slice
          </button>
        )}
        {data.approximate_objects?.some((o) => o.footprint_floor_uv_m) && (
          <label>
            <input
              type="checkbox"
              checked={objects}
              onChange={(e) => setObjects(e.target.checked)}
            />{" "}
            Approximate object footprints
          </label>
        )}
        <label>
          <input
            type="checkbox"
            checked={path}
            onChange={(e) => setPath(e.target.checked)}
          />{" "}
          Capture path
        </label>
        {!!(data.floor_cells.length || data.reviewed_spans.length) && (
          <label>
            <input
              type="checkbox"
              checked={evidence}
              onChange={(e) => setEvidence(e.target.checked)}
            />{" "}
            Reviewed evidence
          </label>
        )}
        <label>
          Point size{" "}
          <input
            type="range"
            min="0.01"
            max="0.065"
            step="0.005"
            value={size}
            onChange={(e) => setSize(Number(e.target.value))}
          />
        </label>
        <label>
          Height slice{" "}
          <input
            type="range"
            min="0.2"
            max="4"
            step="0.1"
            value={height}
            onChange={(e) => setHeight(Number(e.target.value))}
          />
          {height.toFixed(1)} m
        </label>
      </div>
      <p className="viewer-status" role="status">
        {status}
      </p>
      {failure && (
        <p className="error" role="alert">
          {failure}
        </p>
      )}
      <div className="point-cloud-host" ref={host} />
      <p className="viewer-note">
        Height slice removes points above the selected height; disappearance
        alone does not identify a ceiling. Grid spacing is 1 source-estimated
        metre. Furniture is retained. No LiDAR, repaired surfaces, watertight
        mesh or calibrated room dimensions are implied.
      </p>
    </section>
  );
}
