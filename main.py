"""
main.py
-------
The tripAI backend. Run it with:

    uvicorn main:app --reload

Then open http://localhost:8000/docs to try every endpoint.
"""

import os
import json
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from schemas import (
    PlanRequest, PlanResponse, DayPlan,
    ChatRequest, ChatResponse,
    NearbyResponse, NearbySpot,
    WeatherResponse,
)
from rag import retrieve_context

# ---------------------------------------------------------------------------
# FALLBACK_PLAN — Day 8 of your plan: replace this with a real /plan output
# (paste your best demo query's JSON response here) so the demo has
# something solid to show even if the live Gemini call fails.
# ---------------------------------------------------------------------------
FALLBACK_PLAN = {
    "destination": "Madurai",
    "days": 3,
    "itinerary": [
        {
            "day": 1,
            "title": "Temple & Old City",
            "activities": [
                "Visit Meenakshi Amman Temple at sunrise",
                "Walk through the surrounding bazaar streets",
            ],
            "food_suggestions": ["Try a local filter coffee at a nearby stall"],
            "local_tip": "Cover shoulders and knees before entering the temple.",
        },
        {
            "day": 2,
            "title": "Food & Culture",
            "activities": [
                "Explore local markets near the old city",
                "Visit Thirumalai Nayakkar Palace",
            ],
            "food_suggestions": ["Sample Jigarthanda, a Madurai specialty drink"],
            "local_tip": "Bargaining is common and expected in local markets.",
        },
        {
            "day": 3,
            "title": "Wind Down",
            "activities": ["Relax at Vandiyur Mariamman Teppakulam", "Souvenir shopping"],
            "food_suggestions": ["Try a traditional South Indian thali for lunch"],
            "local_tip": "Carry cash, as smaller vendors may not accept cards.",
        },
    ],
    "etiquette_notes": [
        "Dress modestly when visiting temples — shoulders and knees covered.",
        "Remove footwear before entering temple premises.",
    ],
    "sources": [],
}

app = FastAPI(title="tripAI backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

_gemini_model = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        print(f"[warn] Gemini not initialized: {e}")


def call_gemini(prompt: str) -> str | None:
    if not _gemini_model:
        return None
    try:
        response = _gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"[warn] Gemini call failed: {e}")
        return None


@app.get("/")
def root():
    return {"status": "tripAI backend is running", "docs": "/docs"}


# ---------------------------------------------------------------------------
# /plan
# ---------------------------------------------------------------------------
@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest):
    context = retrieve_context(req.destination, req.interests)

    if not context["found"] or not context["verified_spots"]:
        # No real data yet for this destination -> return the fallback
        # so the endpoint always returns *something* usable.
        fallback = dict(FALLBACK_PLAN)
        fallback["destination"] = req.destination
        fallback["days"] = req.days
        return PlanResponse(**fallback)

    prompt = f"""You are a culturally-grounded trip planner. Using ONLY the
verified data below, create a {req.days}-day itinerary for {req.destination}.
Interests: {', '.join(req.interests) if req.interests else 'general'}.
Budget: {req.budget}.

Festivals: {json.dumps(context['festivals'])}
Etiquette: {json.dumps(context['etiquette'])}
Food: {json.dumps(context['food'])}
Verified spots (best match first): {json.dumps(context['verified_spots'])}

Respond ONLY with valid JSON matching this exact shape, no extra text:
{{
  "itinerary": [
    {{"day": 1, "title": "...", "activities": ["..."], "food_suggestions": ["..."], "local_tip": "..."}}
  ],
  "etiquette_notes": ["..."]
}}
"""

    raw = call_gemini(prompt)
    if raw:
        try:
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(cleaned)
            return PlanResponse(
                destination=req.destination,
                days=req.days,
                itinerary=[DayPlan(**d) for d in parsed["itinerary"]],
                etiquette_notes=parsed.get("etiquette_notes", []),
                sources=context["sources"],
            )
        except Exception as e:
            print(f"[warn] Failed to parse Gemini output, using fallback: {e}")

    fallback = dict(FALLBACK_PLAN)
    fallback["destination"] = req.destination
    fallback["days"] = req.days
    fallback["sources"] = context["sources"]
    return PlanResponse(**fallback)


# ---------------------------------------------------------------------------
# /chat
# ---------------------------------------------------------------------------
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    context = retrieve_context(req.destination or "", [])

    prompt = f"""You are a helpful, honest local travel assistant.
Destination context (may be empty): {json.dumps(context)}
User question: {req.message}

Answer helpfully in 2-4 sentences. If you don't have grounded data to
answer accurately, say so honestly rather than inventing facts.
"""
    raw = call_gemini(prompt)
    if raw:
        return ChatResponse(reply=raw.strip(), sources=context.get("sources", []))

    return ChatResponse(
        reply="I don't have a live connection to the AI model right now, "
              "but based on general travel knowledge: please check official "
              "tourism sources for the most accurate answer.",
        sources=context.get("sources", []),
    )


# ---------------------------------------------------------------------------
# /nearby
# ---------------------------------------------------------------------------
@app.get("/nearby", response_model=NearbyResponse)
def nearby(destination: str):
    context = retrieve_context(destination, [])

    if GOOGLE_MAPS_API_KEY:
        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": f"tourist attractions in {destination}", "key": GOOGLE_MAPS_API_KEY},
                timeout=8,
            )
            data = resp.json()
            results = data.get("results", [])[:8]
            if results:
                spots = [
                    NearbySpot(
                        name=r.get("name", "Unknown"),
                        category=", ".join(r.get("types", [])[:2]) or "place",
                        notes=r.get("formatted_address"),
                        lat=r.get("geometry", {}).get("location", {}).get("lat"),
                        lng=r.get("geometry", {}).get("location", {}).get("lng"),
                    )
                    for r in results
                ]
                return NearbyResponse(destination=destination, spots=spots, live_data=True)
        except Exception as e:
            print(f"[warn] Google Maps call failed: {e}")

    # Fallback: curated verified_spots from knowledge_base.json, or empty
    spots = [
        NearbySpot(name=s.get("name", "Unknown"), category=s.get("category", ""), notes=s.get("notes"))
        for s in context.get("verified_spots", [])
    ]
    return NearbyResponse(destination=destination, spots=spots, live_data=False)


# ---------------------------------------------------------------------------
# /weather
# ---------------------------------------------------------------------------
@app.get("/weather", response_model=WeatherResponse)
def weather(destination: str):
    if OPENWEATHER_API_KEY:
        try:
            resp = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": destination, "appid": OPENWEATHER_API_KEY, "units": "metric"},
                timeout=8,
            )
            data = resp.json()
            if resp.status_code == 200:
                return WeatherResponse(
                    destination=destination,
                    available=True,
                    summary=data.get("weather", [{}])[0].get("description"),
                    temp_c=data.get("main", {}).get("temp"),
                    condition=data.get("weather", [{}])[0].get("main"),
                )
        except Exception as e:
            print(f"[warn] OpenWeather call failed: {e}")

    return WeatherResponse(
        destination=destination,
        available=False,
        summary="Live weather unavailable right now — set OPENWEATHER_API_KEY to enable it.",
    )
