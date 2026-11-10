"""Pydantic request/response schemas - these ARE the LLD interface contract."""
from datetime import date as Date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

# API field -> (dataset column, max allowed value, unit)
POLLUTANT_FIELDS = {
    "pm25": ("PM2.5", 1000.0), "pm10": ("PM10", 2000.0), "no2": ("NO2", 1000.0),
    "so2": ("SO2", 2000.0), "co": ("CO", 100.0), "o3": ("O3", 1000.0),
}
MIN_READINGS = 2


class PredictRequest(BaseModel):
    """One city + pollutant readings. Missing readings are filled from city history."""
    city: str = Field(..., min_length=1, examples=["Delhi"])
    date: Optional[Date] = Field(None, description="Used for seasonality; defaults to today")
    pm25: Optional[float] = Field(None, ge=0, le=1000, description="ug/m3")
    pm10: Optional[float] = Field(None, ge=0, le=2000, description="ug/m3")
    no2: Optional[float] = Field(None, ge=0, le=1000, description="ug/m3")
    so2: Optional[float] = Field(None, ge=0, le=2000, description="ug/m3")
    co: Optional[float] = Field(None, ge=0, le=100, description="mg/m3 (NOT ug/m3)")
    o3: Optional[float] = Field(None, ge=0, le=1000, description="ug/m3")

    @model_validator(mode="after")
    def enough_readings(self):
        """Require at least MIN_READINGS pollutant values."""
        given = sum(getattr(self, f) is not None for f in POLLUTANT_FIELDS)
        if given < MIN_READINGS:
            raise ValueError(f"Provide at least {MIN_READINGS} pollutant readings (got {given}).")
        return self


class Prediction(BaseModel):
    """Prediction result for one row."""
    city: str
    category: str
    confidence: float = Field(..., ge=0, le=1)
    probabilities: Dict[str, float]
    color: str
    headline: str
    advice: str
    sensitive_groups: str
    imputed_fields: List[str] = Field(default_factory=list,
                                      description="Readings filled from city history")
    low_confidence: bool = False


class RowError(BaseModel):
    """A batch row that could not be predicted."""
    row: int
    reason: str


class BatchResponse(BaseModel):
    """Batch prediction summary."""
    total: int
    succeeded: int
    failed: int
    results: List[dict]
    errors: List[RowError]


class ErrorResponse(BaseModel):
    """Uniform error body."""
    error: str
    message: str
    details: Optional[list] = None
