from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict

from services.common.enums import CommuteMode


class CommuteMaxModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_label: str
    mode: CommuteMode
    max_min: float


class SearchSpecHardModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    price_max: Optional[float] = None
    price_min: Optional[float] = None
    beds_min: Optional[float] = None
    baths_min: Optional[float] = None
    neighborhoods_include: List[str] = Field(default_factory=list)
    neighborhoods_exclude: List[str] = Field(default_factory=list)
    commute_max: List[CommuteMaxModel] = Field(default_factory=list)
    must_have: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
    available_now: Optional[bool] = None
    move_in_after: Optional[date] = None


class SearchSpecSoftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weights: Dict[str, float] = Field(default_factory=dict)
    nice_to_have: List[str] = Field(default_factory=list)
    vibe: List[str] = Field(default_factory=list)


class SearchSpecExplorationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pct: float = 0.0
    rules: List[str] = Field(default_factory=list)


class SearchSpecModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    search_spec_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    raw_prompt: Optional[str] = None
    hard: SearchSpecHardModel = Field(default_factory=SearchSpecHardModel)
    soft: SearchSpecSoftModel = Field(default_factory=SearchSpecSoftModel)
    exploration: SearchSpecExplorationModel = Field(default_factory=SearchSpecExplorationModel)

    @classmethod
    def default(cls, schema_version: str = "v1") -> "SearchSpecModel":
        return cls(
            schema_version=schema_version,
            search_spec_id=str(uuid4()),
            created_at=datetime.now(tz=timezone.utc),
        )
