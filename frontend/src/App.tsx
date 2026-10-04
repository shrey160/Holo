import { lazy, Suspense, useEffect, useState } from "react";
import { Guide } from "./features/guide/Guide";
import { Input } from "./features/ingestion/Input";
const Reconstruction = lazy(() =>
  import("./features/reconstruction/Reconstruction").then((module) => ({
    default: module.Reconstruction,
  })),
);

export function App() {
  const [tab, setTab] = useState<"guide" | "input" | "reconstruction">(
    window.location.hash === "#reconstruction"
      ? "reconstruction"
      : window.location.hash === "#input"
        ? "input"
        : "guide",
  );
  const [visitedInput, setVisitedInput] = useState(false);
  useEffect(() => {
    const sync = () => {
      const next =
        window.location.hash === "#reconstruction"
          ? "reconstruction"
          : window.location.hash === "#input"
            ? "input"
            : "guide";
      setTab(next);
      if (next === "input") setVisitedInput(true);
    };
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const openTab = (next: "guide" | "input" | "reconstruction") => {
    setTab(next);
    window.history.replaceState(null, "", `#${next}`);
  };
  const openInput = () => {
    setVisitedInput(true);
    openTab("input");
  };
  return (
    <>
      <header className="app-header">
        <div className="header-inner">
          <a className="brand" href="/" aria-label="Holo capture workspace">
            <span className="brand-mark">h</span>
            <strong>
              holo<span>capture workspace</span>
            </strong>
          </a>
          <span className="prototype">PROTOTYPE 02</span>
        </div>
      </header>
      <main>
        <div className="tabs" role="tablist" aria-label="Capture workspace">
          <button
            id="tab-guide"
            role="tab"
            aria-controls="panel-guide"
            aria-selected={tab === "guide"}
            tabIndex={tab === "guide" ? 0 : -1}
            onClick={() => openTab("guide")}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") {
                openInput();
                document.getElementById("tab-input")?.focus();
              }
            }}
          >
            Capture guide
          </button>
          <button
            id="tab-input"
            role="tab"
            aria-controls="panel-input"
            aria-selected={tab === "input"}
            tabIndex={tab === "input" ? 0 : -1}
            onClick={openInput}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft") {
                openTab("guide");
                document.getElementById("tab-guide")?.focus();
              } else if (e.key === "ArrowRight") {
                openTab("reconstruction");
                document.getElementById("tab-reconstruction")?.focus();
              }
            }}
          >
            Input & validation
          </button>
          <button
            id="tab-reconstruction"
            role="tab"
            aria-controls="panel-reconstruction"
            aria-selected={tab === "reconstruction"}
            tabIndex={tab === "reconstruction" ? 0 : -1}
            onClick={() => {
              openTab("reconstruction");
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft") {
                openInput();
                document.getElementById("tab-input")?.focus();
              }
            }}
          >
            Reconstruction
          </button>
        </div>
        <div
          role="tabpanel"
          id="panel-guide"
          aria-labelledby="tab-guide"
          hidden={tab !== "guide"}
        >
          <Guide />
        </div>
        <div
          role="tabpanel"
          id="panel-input"
          aria-labelledby="tab-input"
          hidden={tab !== "input"}
        >
          {(visitedInput || tab === "input") && <Input />}
        </div>
        <div
          role="tabpanel"
          id="panel-reconstruction"
          aria-labelledby="tab-reconstruction"
          hidden={tab !== "reconstruction"}
        >
          {tab === "reconstruction" && (
            <Suspense
              fallback={<p role="status">Loading reconstruction workspace…</p>}
            >
              <Reconstruction />
            </Suspense>
          )}
        </div>
        <footer>
          <span>Holo · capture & reconstruction prototype</span>
          <span>
            Source observations retained. Physical dimensions remain unverified.
          </span>
        </footer>
      </main>
    </>
  );
}
