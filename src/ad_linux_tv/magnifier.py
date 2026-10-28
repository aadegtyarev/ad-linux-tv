"""Validated initial magnifier scale; the compositor applies it at next startup."""


def validate_magnifier(value):
    if not isinstance(value, dict) or set(value) != {"scale"}:
        raise ValueError("magnifier must contain scale")
    scale = value["scale"]
    if type(scale) not in (int, float) or not 1.25 <= scale <= 5 or scale * 4 != int(scale * 4):
        raise ValueError("magnifier scale must be 1.25..5 in steps of0.25")
    return {"scale": float(scale)}
