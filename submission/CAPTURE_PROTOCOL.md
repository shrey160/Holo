# Holo - stock capture protocol

**Supported route:** assisted video, using Sensor Recorder Pro. **Recommended phone:** iPhone 15 or newer. This page covers the completed RGB workflow, not photo reconstruction or LiDAR fusion.

## Install and set up

Install [Sensor Recorder Pro from the App Store](https://apps.apple.com/us/app/sensor-recorder-pro/id6782758613). Tested export: app 1.5, build 5. Allow the camera and motion sensors. Choose **ARKit**, single rear wide camera at **1x**, **1920 x 1080**, **60 Hz**. Enable **IMU, magnetometer, device motion**; leave depth, audio, GeoLoc and barometer off. Auto exposure on; maximum exposure **5 ms**. Keep the current focus setting only if the image is sharp. Do not change lenses or zoom during a session.

## Walk and record

1. Use good lighting, clear the walking path and open connecting doors. Hold the phone in landscape with a consistent grip. Begin **outside the first doorway**. Place one flat A4-sized object on the floor; its full face should be visible. This example uses 21 x 29.7 cm. Object dimensions are retained for later checks and are not used in the automatic reconstruction.
2. Record the object for **3-5 seconds**. Hold briefly, then move sideways a little while keeping its four corners visible. Pan up slowly and cover the doorway corners clockwise, including both jambs, lintel, threshold and surrounding wall.
3. Keep recording while entering toward the centre. Face the doorway wall first; cover it corner to corner clockwise, including floor and ceiling junctions. Repeat for the wall to its right, then the remaining walls. Use slow movements and small translations with overlapping views.
4. Continue through the connector to the next doorway and repeat the doorway/wall sequence. Keep the same uninterrupted recording. **Do not move or record another grounding object.** Finish with a steady view and wait for the recording to save.

Keep the route **under two minutes** for the tested free app configuration. A longer entitlement was not tested. Avoid fast spins, walking with the lens against a wall, dark corners, glare, mirrors as the main view, blocked wall junctions and changing exposure/lens settings midway.

## Hand off the original export

Open the saved session in the app and export/share its **complete original session** to Files. Transfer it to the computer as one ZIP using a file-transfer method you can verify. Check the ZIP contains `wide.mp4`, `meta.json`, `arkit_pose.csv`, `accelerometer.csv`, `gyroscope.csv`, `imu.csv`, `device_motion.csv`, and `magnetometer.csv`. Do not send only the MP4, trim it, or re-encode it. The exact export-button sequence may vary with app version; verify these files before the walk-in session.

In Holo's **Input & validation**, select the ZIP and **Process & reconstruct** with Dense selected. Or use the documented `holo-run` command. An optional separate JPEG/PNG of the same starting object can be attached in Holo; it is retained, not used for automatic scale. Record device/app/OS versions and room order. Take independent laser/tape measurements separately; they are not reconstruction inputs.
