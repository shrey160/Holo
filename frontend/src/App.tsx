import { useState } from "react";
import { Guide } from "./features/guide/Guide";
import { Input } from "./features/ingestion/Input";

export function App() {
  const [tab, setTab] = useState<"guide" | "input">("guide");
  const [visitedInput, setVisitedInput] = useState(false);
  const openInput = () => {
    setVisitedInput(true);
    setTab("input");
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
            onClick={() => setTab("guide")}
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
                setTab("guide");
                document.getElementById("tab-guide")?.focus();
              }
            }}
          >
            Input & validation
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
        <footer>
          <span>Holo · iOS ingestion prototype</span>
          <span>
            Original observations retained. Geometry validation comes next.
          </span>
        </footer>
      </main>
    </>
  );
}
