# Preprocessing review before reconstruction

Reviewed 2026-10-03 on Windows, Python 3.12.14, NumPy 2.5.3 and OpenCV 4.14.0. Scope: inspect the existing iOS RGB/calibration/pose/independent-IMU preparation and select a reconstruction trial. LiDAR, reference dimensions/photo, scale correction and pose refinement remain excluded. Published preprocessing and raw inputs were not changed. No 3D reconstruction or new model installation ran.

## Inputs and method

The two `outputs/*-room-preprocessing-final` datasets passed `verify_preprocessing` against the existing verified ingestion bundles and unchanged `test_data/iphn-17` recordings before review. Contact sheets retain native orientation. Review inspected 2-second timeline samples, all selected endpoints of weak adjacent pairs, and selected views across the double-room 38â€“43-second doorway transition. This is a visual diagnostic review, not exhaustive visibility annotation or proof of every wall/floor boundary.

Reused the preprocessing SIFT matcher at 640 analysis width and its unchanged 20-inlier/0.35-ratio image-support rule. In addition to original neighbors, tested selected-index offsets 2/4/8 and nearby pairs spanning weak boundaries. Then tested up to six source-pose-compatible revisits per view across those review components: more than two seconds apart, less than 40 degrees rotation and less than two metres between source camera centers. This bounded candidate set is not exhaustive place recognition. It uses supplied poses as hypotheses, not independent references.

Retested only the original weak adjacent pairs at 1024 analysis width to assess feature-resolution sensitivity. These diagnostic results do not replace the original report or alter its `REVIEW_REQUIRED` state. Keypoints map back to the native pixel grid. No triangulation was performed.

## Observed matching results

| Diagnostic | Single room | Double room |
|---|---:|---:|
| Selected views | 106 | 240 |
| Original weak adjacent links | 7 | 30 |
| Original adjacent-chain components | 8 | 31 |
| Additional temporal pairs tested / supported | 331 / 164 | 902 / 283 |
| Original weak boundaries with a tested temporal bridge | 0 | 7 |
| Revisit pairs tested / supported | 124 / 54 | 786 / 334 |
| Largest 640-wide image-support component | 100 | 210 |
| Remaining 640-wide components | 6 isolated views | 12-view opening component, two 2-view components, 14 isolated views |
| Original weak adjacent links supported at 1024 width | 1 / 7 | 3 / 30 |
| Largest component when adding the 1024 retests | 101 | 226 |
| Selected views flagged for rapid gyro motion | 5 | 60 |
| Selected views flagged for relative low sharpness | 16 | 10 |

Graph support can come from a fundamental matrix **or** homography. A large image-support component therefore does not establish useful parallax, valid tracks or connected 3D geometry. A stricter exploratory filter requiring at least 20 fundamental-matrix inliers, at least 2 cm source translation and median source-pose Sampson residual at most 3 native pixels gives largest components of only **50 / 144** views. These are proposed diagnostic cutoffs, not validated quality standards. Actual triangulation must check cheirality, parallax, track consistency and reprojection.

Supported original adjacent pairs have median/p90 source-pose Sampson residuals of **1.13 / 3.45 pixels** for single room and **1.41 / 3.82 pixels** for double room. These are conditional on feature matches selected by image geometry and are neither independent pose errors nor centimetre-accuracy evidence.

## Visual findings

**Single room.** The 14.005â€“14.505-second interval pans across the wardrobe; selected frames show blur and limited distinctive texture. Later revisits supply image matches between the main sections, so treating the two weak neighbors as disconnected rooms would be incorrect. Rank 855 at 14.255 seconds remains isolated at 640 width. The final 28.010â€“29.261 seconds look toward a mostly blank upper doorway/wall surface; successive frames have low sharpness and little distinctive image support. The five frames after rank 1680 remain isolated at 640 width. These frames are retained in preprocessing, but a first geometry trial can record them as excluded rather than forcing correspondences. The rest of the recording includes the doorway, bed, wardrobe, desk/window and parts of the floor; furnishing points must not automatically become architectural walls.

**Double room.** Weak endpoints often coincide with rapid turns, blank wall/ceiling areas or polished wardrobe panels. Selected gyro flags affect 60/240 views; this supports investigating capture motion, not automatically deleting a quarter of the observations. Revisited surfaces provide matches beyond immediate neighbors. The 210-view component spans 3.751â€“65.824 seconds and includes views in both rooms. The opening downward views form a separate 12-view component. No reference object dimensions were read or applied.

**Room connection.** The selected 38â€“43-second views retain the inter-room doorway, entrance and nearby surfaces. At 40.548 seconds, source ranks 2431â†’2432 translate **0.06005 m** over approximately one 60-Hz interval, producing the existing apparent 3.60 m/s finding; rotation is approximately 0.99 degrees. Neighboring translation increments are 0.00579 and 0.02354 m. This is an observable source discontinuity/speed event, with cause unverified; images and gyro context cannot establish whether it is actual motion or a tracking correction. Keep it as a marked interval and compare reconstruction behavior there. No smoothing or drift diagnosis was applied.

**Calibration.** Source intrinsics vary per frame. Single-room `cx` spans 957.088â€“964.494 pixels; double-room `cx` spans 957.472â€“966.571. Focal length varies less, approximately 1390.964â€“1391.865 and 1391.182â€“1393.030 pixels. A backend should retain each frame's K rather than silently substituting one shared camera. Distortion and the source's exact pixel-center convention remain unverified.

## Decision

Proceed with a **fixed-pose sparse geometry control on the single room**, with temporal and revisit matching. Keep original K, source world and metre scale, and report views lacking triangulatable support. Do not raise sampling rate globally: the present evidence primarily identifies matching/texture/motion limitations, and a higher frame rate cannot supply missing texture. If the backend finds a specific transition that cannot be supported, a fresh bounded preprocessing run can investigate that interval later.

The first trial should determine whether visual tracks support coherent geometry under supplied cameras. It is not yet a floorplan or dense-surface trial. The [reconstruction plan](../reconstruction/RECONSTRUCTION_PLAN.md) specifies backend, implementation boundaries, input proposal and stop conditions. No reconstruction backend was installed during that review. Subsequent authorized implementation installed PyCOLMAP and executed the sparse trials; see [current results](../reconstruction/RECONSTRUCTION.md).

## Local evidence

These generated files remain ignored and are not submission source or private-media distribution:

- [Initial summary](../../outputs/preconstruction-review-v1/summary.json), [extended summary](../../outputs/preconstruction-review-v1/extended-summary.json), [single detailed review](../../outputs/preconstruction-review-v1/single-review.json), [double detailed review](../../outputs/preconstruction-review-v1/double-review.json).
- [Single revisit/retest details](../../outputs/preconstruction-review-v1/single-extended-review.json), [double revisit/retest details](../../outputs/preconstruction-review-v1/double-extended-review.json), [proposed single-room trial ranks](../../outputs/preconstruction-review-v1/single-trial-input-proposal.json).
- [Single timeline](../../outputs/preconstruction-review-v1/single-timeline.jpg), [single weak frames](../../outputs/preconstruction-review-v1/single-weak-1.jpg), [double timeline](../../outputs/preconstruction-review-v1/double-timeline.jpg), [double doorway transition](../../outputs/preconstruction-review-v1/double-transition.jpg), [double weak endpoints 1](../../outputs/preconstruction-review-v1/double-weak-1.jpg), [2](../../outputs/preconstruction-review-v1/double-weak-2.jpg), [3](../../outputs/preconstruction-review-v1/double-weak-3.jpg).
- Exploratory scripts: [temporal review](../../outputs/preconstruction-review-v1/review.py), [revisit/resolution review](../../outputs/preconstruction-review-v1/extended_review.py). Artifact/input identities are saved in [the review ledger](../../outputs/preconstruction-review-v1/ledger.json).
