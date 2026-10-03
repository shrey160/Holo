# iPhone capture guide

2026-10-03 (Asia/Calcutta). This is the current assisted-RGB development protocol, based on the user's requested movement sequence and the inspected iPhone exports. Settings/export integrity are observed; the full guided route and dimensional accuracy still need validation. Android is deferred.

## Device, app and settings

**iPhone 15 and above is recommended**, with **Sensor Recorder Pro** in ARKit mode. LiDAR is not required for this workflow. The supported exports report **version 1.5, build 5**. Record the actual app/iOS version with every new capture.

| Setting | Value |
|---|---|
| Capture mode | ARKit |
| Camera | Single rear wide camera, 1×; avoid lens changes and digital zoom |
| Resolution | 1920×1080 |
| Camera recording rate | 60 Hz requested; actual supplied rate is approximately 59.98 Hz |
| Auto exposure | On |
| Max exposure | `5` in the photographed UI = 5 ms in exported metadata |
| Focus | Keep current default for this trial: exports report autofocus off and requested lens position about 0.6; verify visible detail is sharp |
| IMU | On: independent accelerometer and gyroscope measurements |
| Magnetometer | On |
| Device motion | On: fused attitude and gravity |
| Barometer, GeoLoc, audio | Off |
| LiDAR depth | Off; depth is not used in this workflow |

Camera Hz is separate from IMU sampling; supplied raw IMU streams run near 100 Hz. Export actual per-frame exposure/focus metadata without assuming requested settings were enforced on every startup frame. Free-mode metadata records a 120-second session limit; plan the route to finish before it ends. Longer-route entitlement has not been tested or purchased here.

## Prepare the space and reference object

- Use a well-lit room and doorway area. Clean the lens, free storage, charge the phone and clear the walking path. Open connecting doors before starting.
- **Always begin outside the first room doorway.** Place the grounding object flat on the ground near the entrance, with enough contrast to see its full boundary.
- The current user-provided reference dimensions are **width 21 cm × height 29.7 cm** (0.210 × 0.297 m). Use a flat A4 sheet or a book face whose actual outer dimensions match these values. Record actual dimensions and uncertainty if measured; a book marketed as A4 need not have an A4-sized outer cover.
- Keep all four corners visible, avoid folded paper/glare/occlusion, and keep the object stationary during its reference views. Do not use the book's thickness as the floor height.
- Use **one grounding object at the start of the video only**. Record it for 3–5 seconds; leave it there when continuing through the rooms. It does not need to appear again or be repositioned at later doorways.
- Optionally take a separate clear photo of that same object, with its whole boundary visible, and attach it in **Input & validation**. JPEG or PNG, up to 10 MiB. The photo is retained for a later grounding check; uploading it does not establish its dimensions or detect it in the video.
- Keep the phone in a consistent landscape grip. Let the AR preview settle before starting where possible. Clockwise below refers to the order in which surfaces are covered, not rolling the phone around the lens axis.

## Record one continuous walkthrough

1. **Grounding object, 3–5 seconds.** Start outside the doorway facing down at the reference. Keep the whole object in view. Hold steady briefly, make a small slow sideways movement if safe while keeping all four corners visible, then pause briefly again. This gives the later scale check multiple viewpoints; avoid a tight crop.
2. **First doorway.** Pan upward smoothly. Record the doorway from corner to corner in clockwise order: upper left, upper right, lower right, lower left. Include both jambs, lintel and threshold, plus some surrounding wall/floor so its relation to the room is visible. Avoid a fast spin.
3. **Enter the room.** Continue recording while walking through the doorway toward somewhere near the room centre. Keep visual overlap with the doorway and nearby wall throughout the transition.
4. **Doorway wall first.** From near the centre, face the wall containing the entry doorway. Sweep it slowly from corner to corner in clockwise order, including floor-wall and ceiling-wall junctions. Keep overlapping views rather than only filming isolated corners.
5. **Continue to the right.** Record the wall to the right in the same way, then the next wall to the right, until all walls are covered. Include openings and obstructed/furnished areas from additional angles where possible. Add small translations when safe; standing in one spot and rotating provides weak triangulation.
6. **Connect to the next room.** Keep recording while moving toward the next room. Film the wall/connector joining the rooms and the approach to its doorway. Preserve overlap through the passage; do not pause, restart or switch modes between rooms.
7. **Repeat at the next doorway.** From outside the next room, record its doorway, entry transition, doorway wall and subsequent walls clockwise. Keep recording continuously with overlap through the connector. The grounding object was already recorded at the start; leave it at the first entrance and continue without another object segment.
8. **Finish.** After the final wall, capture a stable final view for a few seconds, stop and wait for saving. A return along the connector to an earlier view can help later loop-closure work when time permits; it does not itself correct drift.

## Handoff and metadata

Export the **complete original session folder** to Windows. Preserve `wide.mp4`, `arkit_pose.csv`, `meta.json`, `accelerometer.csv`, `gyroscope.csv`, `imu.csv`, `device_motion.csv` and `magnetometer.csv` together. Do not trim the reference-object segment, re-encode video or send only the MP4. Keep ZIP originals where available. Rehearse the installed app's actual export/transfer action; this document does not establish an untested button sequence as a final submission route.

Name the capture and record room order, app/device/settings and the opening reference object's dimensions. Ingestion can retain an explicit scale-prior annotation associated with the source video hash. A first-five-second search window is a candidate for preprocessing, not an assertion that the object is visible in every frame. An optional separate object photo is stored alongside the capture and bound to the same video hash; it does not replace the opening video views.

Independent room measurements belong in an evaluation bundle. Consuming the known-size object is human scale assistance and must be disclosed; these ARKit-assisted recordings do not establish ordinary-video/photo-tier compliance. Keep an ungrounded result available for a later scale-check comparison.

## Using the opening object later

Proposed preprocessing: first manually label the four outer corners in a few sharp frames to validate the geometry, then consider a detector/tracker. ML is optional; corner association and calibrated geometry are the essential parts. Known planar points plus image corners and camera intrinsics can estimate the object's pose relative to the camera. [OpenCV PnP documentation](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html).

For an RGB reconstruction with unknown scale, associate that reference with the same reconstructed cameras/points and estimate one robust global scale using both rectangle dimensions across views. For supplied metric ARKit poses, first compare reconstructed object dimensions against the reference and report disagreement before considering any correction. A single image's centimetres-per-pixel ratio applies to its plane and viewpoint; it cannot be transferred directly to walls at other depths. Planar perspective relationships are described in [OpenCV's homography guide](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html).

The reference may help establish its supporting plane, but does not establish the whole floor, room height, property accuracy or accumulated-drift correction. Object localization, scale estimation/correction and floor inference are deferred until ingestion passes verification. Current dimensions are user-reported, not independently verified physical measurements.
