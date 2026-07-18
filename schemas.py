"""
schemas.py
----------
This file defines the exact SHAPE of data going in and out of every
endpoint. Person 1: you don't need to memorize this, just know that:

  - PlanRequest  = what the frontend SENDS to /plan
  - PlanResponse = what the backend SENDS BACK from /plan
  - ChatRequest / ChatResponse = same idea, for /chat
  - NearbyResponse / WeatherResponse = same idea, for /nearby and /weather

If Person 2 (frontend) says "the app is sending X but expecting Y back",
this is the file to check first.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


# ---------- /plan ----------

class PlanRequest(BaseModel):
    destination: str = Field(..., example="Madurai")
    days: int = Field(..., example=3, ge=1, le=14)
    budget: Optional[str] = Field(default="medium", example="medium")  # low/medium/high
    interests: List[str] = Field(default_factory=list, example=["food", "temples", "culture"])


class DayPlan(BaseModel):
    day: int
    title: str
    activities: List[str]
    food_suggestions: List[str] = Field(default_factory=list)
    local_tip: Optional[str] = None


class PlanResponse(BaseModel):
    destination: str
    days: int
    itinerary: List[DayPlan]
    etiquette_notes: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


# ---------- /chat ----------

class ChatRequest(BaseModel):
    destination: Optional[str] = Field(default=None, example="Madurai")
    message: str = Field(..., example="What should I wear when visiting the temple?")


class ChatResponse(BaseModel):
    reply: str
    sources: List[str] = Field(default_factory=list)


# ---------- /nearby ----------

class NearbySpot(BaseModel):
    name: str
    category: str
    notes: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class NearbyResponse(BaseModel):
    destination: str
    spots: List[NearbySpot]
    live_data: bool  # True if Google Maps API key was used, False if curated fallback


# ---------- /weather ----------

class WeatherResponse(BaseModel):
    destination: str
    available: bool
    summary: Optional[str] = None
    temp_c: Optional[float] = None
    condition: Optional[str] = None
