"""Validated user metadata. Geometry remains outside this application layer."""

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PhotosReference(BaseModel):
    """Declared known-size object for the photo tier; dimensions are never applied."""

    model_config = ConfigDict(extra="forbid")
    object_id: str = Field(default="a4-reference-1", min_length=1, max_length=64)
    width_m: float = Field(gt=0, le=100, allow_inf_nan=False)
    height_m: float = Field(gt=0, le=100, allow_inf_nan=False)
    reference_asset: str | None = Field(default=None, max_length=300)
    candidate_assets: list[str] = Field(default_factory=list, max_length=16)

    def declaration(self) -> dict:
        return {
            "object_id": self.object_id,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "reference_asset": self.reference_asset,
            "candidate_assets": list(self.candidate_assets),
            "provenance": "USER_DECLARED",
        }


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width_cm: float = Field(gt=0, le=1000, allow_inf_nan=False)
    height_cm: float = Field(gt=0, le=1000, allow_inf_nan=False)
    start_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    end_seconds: float = Field(default=5, gt=0, allow_inf_nan=False)
    placement: str = Field(default="on the ground at the opening", max_length=300)

    @model_validator(mode="after")
    def ordered_window(self):
        if not math.isfinite(self.end_seconds) or self.end_seconds <= self.start_seconds:
            raise ValueError("Reference end must follow start")
        return self

    def annotation(self, video_hash: str) -> dict:
        return {
            "schema_version": 1,
            "source_video_sha256": video_hash,
            "reference_objects": [
                {
                    "id": "opening-reference",
                    "label": "user-declared reference object",
                    "width_m": self.width_cm / 100,
                    "height_m": self.height_cm / 100,
                    "dimensions_source": "USER_REPORTED",
                    "dimension_uncertainty_m": None,
                    "candidate_window_seconds": [self.start_seconds, self.end_seconds],
                    "visibility_verified": False,
                    "placement": self.placement,
                    "usage": "human scale prior; no geometry correction during ingestion",
                }
            ],
        }
