# Raw benchmark data inventory

Included: [single_room.zip](../example_data/video/single_room.zip), 33,808,090 bytes, SHA-256 `815cffe1c1b7a7f4e1670364d2d399f9110c3c3975e9c23994a3ac06d2f34d8c`. The [asset manifest](../example_data/video/manifest.json) lists all eight original files and hashes. ZIP CRC is checked during final validation. The archive is copied unchanged from the author's `test_data/iphn-17/zips` directory.

| Export asset | Role |
|---|---|
| `wide.mp4` | Original RGB video; 1,756 camera frames |
| `arkit_pose.csv` | Source camera clock, intrinsics, fixed poses and tracking |
| `accelerometer.csv`, `gyroscope.csv`, `imu.csv` | Original independent/combined IMU measurements |
| `device_motion.csv` | Exported fused motion/gravity |
| `magnetometer.csv` | Original magnetic field measurements |
| `meta.json` | App/device/settings/version/convention declarations |

The dataset is one room, not the required >=3-room-plus-connector all-tier property benchmark. It has no labelled two-class staged-damage set. The double-room export and photo/Stray fixtures used in earlier development remain outside this submission's included example; their availability does not establish a three-tier benchmark on the same property.

[ground-truth.json](raw/ground-truth.json) records only the actual user statements: A4 face 0.21 x 0.297 m, thickness below 1 cm, and ceiling about 2.6 m. Instruments and uncertainty were not recorded. The A4 dimensions are not held-out room truth; the approximate ceiling cannot support the 1.5 cm gate. None were used by the automatic reconstruction. Earlier roughly 3 x 4 m descriptions are inferred-plan comparisons, not tape/laser ground truth.

**Missing:** laser/tape wall/opening/ceiling/area ledger; separate repeated captures of the same room/tier; matched three-tier property inputs; fresh versioned Pro LiDAR export; consumer-app name/version and actual room exports; damage classes/extent labels and concealed/scope references. [Machine-readable missing-data ledger](raw/missing-data.json). Empty or missing data are not assigned zero error or a pass.
