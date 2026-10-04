"""Portable numeric report comparison; categorical decisions and counts stay exact."""

import math


def equivalent(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b, strict=True))
    if type(a) is float and type(b) is float:
        return (
            math.isfinite(a)
            and math.isfinite(b)
            and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-10)
        )
    return type(a) is type(b) and a == b
