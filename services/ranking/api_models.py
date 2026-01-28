from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RankOptionsModel(BaseModel):
    limit: int = 50


class RankRequestModel(BaseModel):
    schema_version: str
    search_spec_id: str
    options: Optional[RankOptionsModel] = None
