import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Viewer } from "@mkkellogg/gaussian-splats-3d";
import type { GaussianResult } from "./GaussianViewer";

export default function SplatCanvas({ result }: { result: GaussianResult }) {
  const host = useRef<HTMLDivElement>(null),
    reset = useRef<() => void>(() => {}),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!host.current) return;
    const element = document.createElement("div");
    element.className = "gaussian-canvas";
    host.current.appendChild(element);
    let viewer: Viewer | undefined,
      renderer: THREE.WebGLRenderer | undefined,
      controls: OrbitControls | undefined,
      observer: ResizeObserver | undefined,
      frame = 0,
      disposed = false;
    setError("");
    setLoading(true);
    try {
      renderer = new THREE.WebGLRenderer({ antialias: false });
      renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
      renderer.setClearColor(0x202725);
      element.appendChild(renderer.domElement);
      renderer.domElement.tabIndex = 0;
      renderer.domElement.setAttribute(
        "aria-label",
        "Interactive Gaussian room reconstruction. Drag to orbit, right drag to pan, scroll to zoom.",
      );
      const camera = new THREE.PerspectiveCamera(65, 1, 0.05, 100);
      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.listenToKeyEvents(renderer.domElement);
      reset.current = () => {
        camera.position.fromArray(result.camera_position);
        controls!.target.fromArray(result.camera_target);
        controls!.update();
      };
      reset.current();
      camera.updateMatrixWorld();
      renderer.setSize(element.clientWidth, element.clientHeight);
      viewer = new Viewer({
        rootElement: element,
        renderer,
        camera,
        selfDrivenMode: false,
        useBuiltInControls: false,
        gpuAcceleratedSort: false,
        sharedMemoryForWorkers: false,
        enableSIMDInSort: false,
        sphericalHarmonicsDegree: 0,
        ignoreDevicePixelRatio: false,
        halfPrecisionCovariancesOnGPU: true,
      });
      observer = new ResizeObserver(() => {
        const { width, height } = element.getBoundingClientRect();
        renderer!.setSize(width, height);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      });
      observer.observe(element);
      viewer
        .addSplatScene(`/api/gaussians/${result.id}/room.splat`, {
          showLoadingUI: false,
          splatAlphaRemovalThreshold: 1,
        })
        .then(() => {
          if (disposed) return;
          setLoading(false);
          const animate = () => {
            if (disposed) return;
            controls!.update();
            viewer!.update();
            viewer!.render();
            element.dataset.drawCalls = String(renderer!.info.render.calls);
            element.dataset.instances = String(
              viewer!.getSplatMesh().geometry.instanceCount,
            );
            frame = requestAnimationFrame(animate);
          };
          animate();
        })
        .catch((e: Error) => {
          if (!disposed) {
            setError(e.message);
            setLoading(false);
          }
        });
    } catch (e) {
      setError((e as Error).message);
      setLoading(false);
    }
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer?.disconnect();
      controls?.dispose();
      reset.current = () => {};
      const release = () => {
        renderer?.dispose();
        element.remove();
      };
      if (viewer)
        void viewer
          .dispose()
          .catch(() => {})
          .finally(release);
      else release();
    };
  }, [result]);
  return (
    <div className="gaussian-view">
      <div className="viewer-toolbar">
        <button className="secondary" onClick={() => reset.current()}>
          Reset Gaussian view
        </button>
        <span>Drag to orbit · right drag to pan · scroll to zoom</span>
      </div>
      {loading && <p role="status">Loading Gaussian scene…</p>}
      {error && (
        <p className="error" role="alert">
          Gaussian rendering unavailable: {error}. Use the point-cloud view or
          download the scene.
        </p>
      )}
      <div ref={host} />
    </div>
  );
}
