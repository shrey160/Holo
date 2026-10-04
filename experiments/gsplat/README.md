# Isolated gsplat GPU worker

This uv project intentionally uses Python 3.10 because the pinned official gsplat 1.5.3/PyTorch 2.4/CUDA 12.4 compiled Linux wheel targets CPython 3.10. It is independent of Holo's Python 3.12 project. [Full experiment contract and commands](../../GAUSSIANS.md).

Build with `docker build -t holo-gsplat:0.1.0 experiments/gsplat` from prototype-2, or use `uv sync --locked` here on native Linux. Inputs must be prepared and audited by `cozmo-gaussians prepare`. Mount inputs read-only and only the new experiment output parent writable. Run `worker.py INPUTS NEW_OUTPUT --steps 10000 --deadline 900`. No global Python installation or modification of the main venv is required.

The worker retains paired initial/final validation images, model arrays, per-view quality/coverage, runtime/GPU/dependency/code identity and a content-hashed trial manifest. It raises on timeout/non-finite loss/input mutation. A partial result without the completed manifest is not publishable. Portable Holo scene publication is a separate CPU command; no GPU is needed to view the result.

The selected single-room trial used 10,000 steps and reached 21.94 dB mean photometric holdout PSNR / 0.789 local SSIM. Run `docker run --rm --gpus all --entrypoint /worker/.venv/bin/python holo-gsplat:0.1.0 /worker/probe.py` to check actual CUDA forward/backward kernels before training. The lock includes packaging/setuptools needed by the pinned compiled wheel. See the full contract for source overlap and physical-accuracy limits.
