"""Offline corner editor and inspectable source/residual images."""

import json
import shutil

import cv2
import numpy as np

from .annotations import template
from .geometry import project


def write_review(stage, prepared, identity, object_id, views, annotations, report):
    (stage / "images").mkdir()
    by_rank = {r["rank"]: r for r in annotations["observations"]}
    tri = report["unconstrained_triangulation"]
    for view in views:
        name = f"{view['rank']:06d}.jpg"
        shutil.copyfile(prepared / view["image"], stage / "images" / name)
        if view["rank"] not in by_rank:
            continue
        rgb = cv2.imread(str(stage / "images" / name))
        xy = np.array(by_rank[view["rank"]]["corners_native"])
        cv2.polylines(rgb, [np.rint(xy - 0.5).astype(np.int32)], True, (0, 220, 255), 3)
        for index, point in enumerate(xy):
            cv2.putText(
                rgb,
                str(index),
                tuple(np.rint(point + [6, -6]).astype(int)),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 220, 255),
                2,
            )
        if tri["corners_world_m"] is not None:
            projected, depths = project(view["camera"], tri["corners_world_m"])
            if np.isfinite(projected).all() and (depths > 0).all():
                for observed, predicted in zip(xy, projected, strict=True):
                    cv2.line(
                        rgb,
                        tuple(np.rint(observed - 0.5).astype(int)),
                        tuple(np.rint(predicted - 0.5).astype(int)),
                        (0, 0, 255),
                        3,
                    )
                    cv2.circle(
                        rgb, tuple(np.rint(predicted - 0.5).astype(int)), 5, (255, 180, 0), 2
                    )
        (stage / "overlays").mkdir(exist_ok=True)
        if not cv2.imwrite(str(stage / "overlays" / name), rgb):
            raise OSError("Grounding overlay write failed")
    payload = {
        "template": template(identity, object_id),
        "annotations": annotations,
        "views": [
            {
                k: v[k]
                for k in ("rank", "frame_id", "relative_seconds", "image_sha256", "image_size")
            }
            for v in views
        ],
        "report": report,
    }
    # Escape '<' to prevent an annotation note from terminating the JSON script element.
    data = json.dumps(payload, allow_nan=False).replace("<", "\\u003c")
    html = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Holo · Grounding review</title><style>
body{font:16px system-ui;background:#f6f7f2;color:#203e38;margin:0}main{max-width:1100px;margin:auto;padding:24px}
button,select,input{font:inherit;padding:10px;margin:5px}button{cursor:pointer}canvas{width:100%;height:auto;display:block;background:#ddd;touch-action:none}
.panel{background:white;padding:20px;margin:20px 0;border:1px solid #d6e3d8;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}textarea{width:100%;min-height:160px;box-sizing:border-box}summary{cursor:pointer;margin:12px 0}
label{display:inline-block}#notice{color:#7b3d19}a{color:#116c60}</style><main>
<h1>Holo · Grounding diagnostic</h1><p>One opening reference. Fixed cameras. Scale unchanged.</p>
<div class="panel"><h2>Result</h2><p id="result"></p><p id="notice"></p><p id="summary"></p><a href="report.json">Full report</a> · <a href="manifest.json">Provenance</a><details><summary>Detailed diagnostics</summary><pre id="metrics"></pre></details></div>
<div class="panel" id="investigation" hidden><h2>Mismatch investigation</h2><p id="investigationSummary"></p><p>These controlled checks preserve the recorded camera poses and corner marks. They do not apply a correction or identify a unique cause.</p><details><summary>Controlled experiment results</summary><pre id="experimentDetails"></pre></details></div>
<div class="panel"><h2>Review the cover corners</h2><p>Click the same four physical corners in every frame. Edge 0→1 is the short width; 1→2 is the long height. Trace the outer cover, excluding spiral wire. For rounded corners use straight-edge intersections consistently. Skip blurred or occluded views. Native image orientation is retained.</p>
<select id="frames" aria-label="Reference frame"></select><button id="reset">Reset this frame</button><button id="undo">Undo corner</button>
<p id="frameInfo"></p><canvas id="image" aria-label="Mark four reference corners"></canvas><p id="coordinates"></p>
<label>Annotator <input id="annotator" placeholder="Your name or identifier"></label>
<label><input id="reviewed" type="checkbox">I reviewed all exported corners and edge identities</label>
<p>Only frames with four corners are exported. Exporting downloads a separate JSON; it does not change this report. Rerun the CLI with that JSON to calculate an updated report.</p>
<button id="export">Download corners JSON</button><input id="import" type="file" accept="application/json" aria-label="Import corners JSON"><p id="feedback" role="status"></p><textarea id="exportText" aria-label="Exported corners JSON" readonly hidden></textarea></div>
<div class="panel"><h2>Recorded overlays</h2><div id="overlays"></div></div></main>
<script id="data" type="application/json">PAYLOAD</script><script>
const data=JSON.parse(document.getElementById('data').textContent), $=id=>document.getElementById(id);
const marked=new Map(data.annotations.observations.map(r=>[r.rank,r.corners_native]));
const canvas=$('image'),ctx=canvas.getContext('2d'); let photo=new Image(),loadGeneration=0;
$('result').textContent=data.report.geometry_state;
$('notice').textContent='Physical accuracy unverified. '+(data.report.human_reviewed_corners?'Corners confirmed by human review.':'Corner proposals require human review.')+' '+(data.report.cover_thickness_bound?'Thickness is bounded below 1 cm; exact thickness is unknown. Floor-height comparison is '+data.report.floor_comparison_status.toLowerCase()+'.':'Book thickness remains '+(data.annotations.cover_thickness_m===null?'unknown.':'a user assumption.'));
const tri=data.report.unconstrained_triangulation;
$('summary').textContent=`Marked ${data.report.annotated_views} views. `+(tri.reprojection_max_pixels===undefined?'Corner geometry is not yet supported.':`Maximum corner residual ${tri.reprojection_max_pixels.toFixed(2)} px; the acceptance limit is 4 px. Exploratory size values require this geometry check and corner review.`);
$('metrics').textContent=JSON.stringify({size_check:data.report.size_check,sensitivity:data.report.sensitivity,supplemental:data.report.supplemental},null,2);
$('annotator').value=data.annotations.annotator; $('reviewed').checked=data.report.human_reviewed_corners;
const diagnostic=data.report.mismatch_diagnostics;
if(diagnostic){$('investigation').hidden=false;$('experimentDetails').textContent=JSON.stringify(diagnostic,null,2);if(diagnostic.status==='COMPUTED'){$('investigationSummary').textContent=`Largest residual: corner ${diagnostic.dominant_residual.corner_index} at frame ${diagnostic.dominant_residual.rank}. Minimizing pixel error for the 3D corner points gives a maximum residual of ${diagnostic.pixel_objective_point_fit.reprojection_max_pixels.toFixed(2)} px. Floor and scale remain unresolved.`;}else{$('investigationSummary').textContent='Not enough supported geometry for controlled experiments.';}}
for(const v of data.views){const option=document.createElement('option');option.value=v.rank;option.textContent=`Frame ${v.rank} · ${Number(v.relative_seconds).toFixed(3)} s`;$('frames').append(option);}
function current(){return data.views.find(v=>v.rank===Number($('frames').value));}
function draw(){const v=current();if(!v)return;ctx.drawImage(photo,0,0);const xy=marked.get(v.rank)||[];ctx.strokeStyle='#ffca28';ctx.fillStyle='#ffca28';ctx.lineWidth=3;ctx.font='28px system-ui';ctx.beginPath();xy.forEach((p,i)=>{if(i===0)ctx.moveTo(...p);else ctx.lineTo(...p);ctx.fillText(String(i),p[0]+8,p[1]-8);});if(xy.length===4)ctx.closePath();ctx.stroke();$('coordinates').textContent=JSON.stringify(xy.map(p=>p.map(n=>Number(n.toFixed(2)))))+` · ${xy.length}/4 corners`;}
function load(){const v=current();if(!v)return;const generation=++loadGeneration;const next=new Image();next.onload=()=>{if(generation!==loadGeneration)return;photo=next;canvas.width=v.image_size[0];canvas.height=v.image_size[1];$('frameInfo').textContent=`Native ${canvas.width} × ${canvas.height} · ${v.frame_id}`;draw();};next.src=`images/${String(v.rank).padStart(6,'0')}.jpg`;}
$('frames').onchange=load;
canvas.onclick=e=>{const v=current();if(!v)return;const box=canvas.getBoundingClientRect(),xy=marked.get(v.rank)||[];if(xy.length===4)return;xy.push([(e.clientX-box.left)*canvas.width/box.width,(e.clientY-box.top)*canvas.height/box.height]);marked.set(v.rank,xy);$('reviewed').checked=false;draw();};
$('reset').onclick=()=>{marked.delete(current().rank);$('reviewed').checked=false;draw();};
$('undo').onclick=()=>{const xy=marked.get(current().rank)||[];xy.pop();marked.set(current().rank,xy);$('reviewed').checked=false;draw();};
$('export').onclick=()=>{if(!$('annotator').value.trim()){$('feedback').textContent='Enter an annotator identifier.';return;}
const output={...data.annotations,annotator:$('annotator').value.trim(),human_reviewed:$('reviewed').checked,observations:data.views.filter(v=>(marked.get(v.rank)||[]).length===4).map(v=>({...v,corners_native:marked.get(v.rank)}))};
if(output.observations.length>12){$('feedback').textContent='Select at most 12 marked frames.';return;}
const serialized=JSON.stringify(output,null,2)+'\\n';$('exportText').value=serialized;$('exportText').hidden=false;
const url=URL.createObjectURL(new Blob([serialized],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='grounding-corners.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('feedback').textContent=`Prepared ${output.observations.length} frames. If the browser blocks the download, copy the JSON below into a separate file. Rerun the diagnostic CLI.`;};
$('import').onchange=async e=>{try{const incoming=JSON.parse(await e.target.files[0].text());for(const key of ['schema','prepared_manifest_sha256','ingestion_manifest_sha256','source_video_sha256','sparse_manifest_sha256','dense_manifest_sha256','surfaces_manifest_sha256','object_id','pixel_convention','corner_order'])if(incoming[key]!==data.annotations[key])throw new Error('Different source or coordinate convention');const replacement=new Map();for(const row of incoming.observations){const v=data.views.find(v=>v.rank===row.rank);if(!v||v.image_sha256!==row.image_sha256||v.frame_id!==row.frame_id||!Array.isArray(row.corners_native)||row.corners_native.length!==4)throw new Error('Invalid frame');if(!row.corners_native.every(p=>p.length===2&&p.every(Number.isFinite)&&p[0]>=0&&p[1]>=0&&p[0]<v.image_size[0]&&p[1]<v.image_size[1]))throw new Error('Invalid corners');replacement.set(row.rank,row.corners_native);}marked.clear();for(const [rank,xy] of replacement)marked.set(rank,xy);$('annotator').value=incoming.annotator;$('reviewed').checked=false;draw();$('feedback').textContent='Imported; review before export. CLI performs full validation.';}catch(error){$('feedback').textContent=error.message;}};
for(const row of data.annotations.observations){const p=document.createElement('p');p.textContent=`Frame ${row.rank}: yellow observed corners; blue fixed-camera reprojection; red residuals.`;const im=document.createElement('img');im.src=`overlays/${String(row.rank).padStart(6,'0')}.jpg`;im.style.width='100%';im.alt=`Reference corners and residuals at frame ${row.rank}`;$('overlays').append(p,im);}
load();</script></html>"""
    (stage / "index.html").write_text(html.replace("PAYLOAD", data), encoding="utf-8")
