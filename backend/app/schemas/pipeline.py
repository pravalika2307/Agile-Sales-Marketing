"""Pipeline and PipelineStage Pydantic schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PipelineStageCreate(BaseModel):
    """Payload to create a new pipeline stage."""
    name: str = Field(..., min_length=1, max_length=255, description="Stage name")
    order_index: int = Field(0, ge=0, description="Visual ordering index")
    probability_pct: int = Field(0, ge=0, le=100, description="Win probability percentage (0-100)")

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Stage name cannot be empty or whitespace only.")
        return clean


class PipelineStageUpdate(BaseModel):
    """Payload to partially update a pipeline stage."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    order_index: Optional[int] = Field(None, ge=0)
    probability_pct: Optional[int] = Field(None, ge=0, le=100)

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("Stage name cannot be empty or whitespace only.")
            return clean
        return v


class PipelineStageResponse(BaseModel):
    """Pipeline stage public representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pipeline_id: uuid.UUID
    name: str
    order_index: int
    probability_pct: int
    created_at: datetime
    updated_at: datetime


class PipelineCreate(BaseModel):
    """Payload to create a new Sales Pipeline."""
    name: str = Field(..., min_length=1, max_length=255, description="Pipeline name")
    is_default: Optional[bool] = Field(False, description="Whether this is the default pipeline")

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Pipeline name cannot be empty or whitespace only.")
        return clean


class PipelineUpdate(BaseModel):
    """Payload to partially update an existing Pipeline."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_default: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("Pipeline name cannot be empty or whitespace only.")
            return clean
        return v


class PipelineResponse(BaseModel):
    """Pipeline public representation including ordered stages."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    stages: List[PipelineStageResponse] = Field(default_factory=list)
