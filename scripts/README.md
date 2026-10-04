# Runtime setup scripts

`install-native-colmap.ps1` installs the official pinned COLMAP 4.2.1 Windows CUDA archive into ignored project-local `.tools/colmap`. It verifies the release SHA-256 before extraction, leaves system PATH unchanged and does not download Python or model dependencies.

Run from PowerShell with `./scripts/install-native-colmap.ps1`. Holo discovers the project-local executable when launched from `proto-2`; other working directories can set `COLMAP_EXECUTABLE` explicitly. A usable NVIDIA GPU/driver and the existing `web` + `reconstruct` Python extras are required. [Complete setup](../NATIVE_DENSE.md).
