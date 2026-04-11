"""
Pydantic models for API request/response schemas.
"""

from pydantic import BaseModel
from typing import Any, Optional
from datetime import datetime


class StandardResponse(BaseModel):
    success: bool = True
    data: Any = None
    meta: Optional[dict] = None


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    success: bool = True
    response: str
    template: Optional[str] = None
    confidence: Optional[float] = None
    data: Any = None
    meta: Optional[dict] = None


class CountPartsRequest(BaseModel):
    image_base64: str
    context: Optional[str] = None


class CountPartsResponse(BaseModel):
    success: bool = True
    count: int = 0
    confidence: str = "low"  # high, medium, low
    description: str = ""
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None
