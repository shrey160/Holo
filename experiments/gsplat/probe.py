"""Exercise compiled forward/backward kernels, not merely package imports."""

import json

import gsplat
import torch
from gsplat import rasterization

means = torch.tensor([[0.0, 0.0, 2.0]], device="cuda", requires_grad=True)
quats = torch.tensor([[1.0, 0.0, 0.0, 0.0]], device="cuda")
scales = torch.full((1, 3), 0.03, device="cuda")
opacity = torch.ones(1, device="cuda")
colors = torch.ones((1, 3), device="cuda")
view = torch.eye(4, device="cuda")[None]
intrinsics = torch.tensor([[[50.0, 0.0, 32.0], [0.0, 50.0, 32.0], [0.0, 0.0, 1.0]]], device="cuda")
render, _, _ = rasterization(means, quats, scales, opacity, colors, view, intrinsics, 64, 64)
render.sum().backward()
assert torch.isfinite(render).all() and torch.isfinite(means.grad).all()
print(
    json.dumps(
        {
            "status": "CUDA_FORWARD_BACKWARD_PASSED",
            "torch": torch.__version__,
            "gsplat": gsplat.__version__,
            "gpu": torch.cuda.get_device_name(),
        }
    )
)
