import { useState } from "react";
import guide from "../../../../capture.md?raw";
import { Markdown } from "../../components/Markdown";

const sections = Object.fromEntries(
  guide
    .split(/^## /m)
    .slice(1)
    .map((section) => {
      const newline = section.indexOf("\n");
      return [section.slice(0, newline).trim(), section.slice(newline).trim()];
    }),
);
const steps = sections["Record one continuous walkthrough"]
  .split(/^\d+\. /m)
  .filter(Boolean);
const title = (step: string) =>
  step.match(/^\*\*(.*?)\*\*/)?.[1].replace(/\.$/, "") || "Capture step";

function RouteDiagram({ step }: { step: number }) {
  return (
    <svg
      viewBox="0 0 400 280"
      role="img"
      aria-label="Room capture sequence: begin outside the doorway, enter the centre, cover walls clockwise and connect to the next room"
    >
      <defs>
        <marker
          id="arrow"
          markerWidth="8"
          markerHeight="8"
          refX="6"
          refY="3"
          orient="auto"
        >
          <path d="M0,0 L6,3 L0,6" fill="#167665" />
        </marker>
      </defs>
      <rect width="400" height="280" fill="#f3f5ef" rx="20" />
      <path
        d="M75 215 V45 H290 V215 H225 M165 215 H75"
        fill="white"
        stroke="#445c54"
        strokeWidth="7"
      />
      <path
        d="M290 80 H357 V190 H290"
        fill="none"
        stroke="#a7b9ac"
        strokeWidth="5"
      />
      <path
        d="M165 215 V160 A55 55 0 0 1 220 215"
        fill="none"
        stroke="#a7b9ac"
        strokeDasharray="4 4"
      />
      <rect
        x="172"
        y="240"
        width="23"
        height="30"
        rx="2"
        fill={step === 0 ? "#edb254" : "#d5dfd4"}
        stroke="#8d9b88"
      />
      <path
        d="M199 244 V134"
        stroke="#167665"
        strokeWidth="3"
        strokeDasharray="6 6"
        markerEnd="url(#arrow)"
      />
      <circle cx="199" cy="134" r="13" fill="#167665" />
      <circle cx="199" cy="134" r="4" fill="white" />
      <path
        d="M103 182 V74 H259 V181"
        fill="none"
        stroke="#167665"
        strokeWidth="2.5"
        markerEnd="url(#arrow)"
        opacity={step >= 3 ? 1 : 0.25}
      />
      <text x="115" y="115" fill="#73847a" fontSize="12">
        ROOM 01
      </text>
      <text x="303" y="140" fill="#73847a" fontSize="11">
        NEXT
      </text>
      <text x="207" y="260" fill="#62796f" fontSize="11">
        START OUTSIDE
      </text>
      <text x="90" y="203" fill="#62796f" fontSize="10">
        DOORWAY WALL FIRST
      </text>
    </svg>
  );
}

export function Guide() {
  const [step, setStep] = useState(0);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">01 / BEFORE YOU RECORD</span>
          <h1>
            A good capture starts
            <br />
            with a clear route.
          </h1>
          <p>
            One continuous walkthrough. Consistent settings. Complete exports.
          </p>
        </div>
        <span className="pill">iPhone · Assisted RGB</span>
      </div>
      <section className="walkthrough panel">
        <div className="route">
          <RouteDiagram step={step} />
          <span className="caption">
            Clockwise means surface order. Keep a consistent phone grip.
          </span>
        </div>
        <div className="step-content">
          <span className="eyebrow">
            THE WALKTHROUGH · {String(step + 1).padStart(2, "0")} /{" "}
            {String(steps.length).padStart(2, "0")}
          </span>
          <h2>{title(steps[step])}</h2>
          <Markdown>{steps[step].replace(/^\*\*.*?\*\*\s*/, "")}</Markdown>
          <div className="step-actions">
            <button
              className="secondary"
              disabled={step === 0}
              onClick={() => setStep(step - 1)}
            >
              ← Previous
            </button>
            <button
              className="primary"
              disabled={step === steps.length - 1}
              onClick={() => setStep(step + 1)}
            >
              Next step →
            </button>
          </div>
        </div>
        <div className="step-nav" aria-label="Capture steps">
          {steps.map((item, index) => (
            <button
              key={index}
              className={step === index ? "selected" : ""}
              aria-current={step === index ? "step" : undefined}
              onClick={() => setStep(index)}
            >
              <span>{index + 1}</span>
              {title(item)}
            </button>
          ))}
        </div>
      </section>
      <div className="guide-grid">
        <section className="panel section">
          <span className="eyebrow">PREPARATION</span>
          <h2>Set up the space</h2>
          <Markdown>
            {sections["Prepare the space and reference object"]}
          </Markdown>
        </section>
        <section className="panel section">
          <span className="eyebrow">DEVICE CHECKLIST</span>
          <h2>App & camera settings</h2>
          <Markdown>{sections["Device, app and settings"]}</Markdown>
        </section>
      </div>
      <section className="panel section">
        <span className="eyebrow">AFTER THE WALKTHROUGH</span>
        <h2>Bring the complete export</h2>
        <Markdown>{sections["Handoff and metadata"]}</Markdown>
      </section>
      <details className="panel section">
        <summary>How the known-size object will be used later</summary>
        <Markdown>{sections["Using the opening object later"]}</Markdown>
      </details>
    </>
  );
}
