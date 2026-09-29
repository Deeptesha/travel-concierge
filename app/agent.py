# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import uuid
from zoneinfo import ZoneInfo

import google.auth
from google.auth.transport.requests import Request
from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types
import requests

from app.a2ui_utils import a2ui_callback

PROJECT_ID = "qwiklabs-gcp-01-f3f508531c62"
COLLECTION_NAME = "destinations"
BUCKET_NAME = "travel-concierge-media-qwiklabs-gcp-01-f3f508531c62"

# Initialize Firestore client with hardcoded project ID
db = firestore.Client(project=PROJECT_ID)


def _get_google_api_headers() -> dict:
    credentials, _ = google.auth.default()
    credentials.refresh(Request())
    return {
        "Authorization": f"Bearer {credentials.token}",
        "X-Goog-User-Project": PROJECT_ID,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        "Content-Type": "application/json",
    }


def geocode_address(address: str) -> dict:
    """Turn an address or landmark name into geographic coordinates, official name, and formatted address.

    Args:
        address: Address or landmark string (e.g. 'Eiffel Tower, Paris', 'Shinjuku Station, Tokyo').

    Returns:
        Dictionary with key fields: name, address, and location (latitude/longitude).
    """
    try:
        headers = _get_google_api_headers()
        body = {"textQuery": address}
        resp = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers=headers,
            json=body,
            timeout=10,
        )
        data = resp.json()
        if not data.get("places"):
            return {"error": f"Address '{address}' not found."}

        place = data["places"][0]
        return {
            "name": place.get("displayName", {}).get("text", address),
            "address": place.get("formattedAddress"),
            "location": place.get("location"),
        }
    except Exception as e:
        return {"error": f"Failed to geocode address: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "restaurant",
    radius_meters: float = 1000.0,
) -> list[dict]:
    """Find nearby places of a given type around a geographic coordinate point using Google Places API (New).

    Args:
        latitude: Latitude coordinate of the central point.
        longitude: Longitude coordinate of the central point.
        place_type: Type of place to search for (e.g. 'restaurant', 'cafe', 'museum', 'park', 'tourist_attraction', 'hotel').
        radius_meters: Search radius in meters (default 1000m).

    Returns:
        List of dictionaries containing key fields: name, address, and location.
    """
    try:
        headers = _get_google_api_headers()
        body = {
            "includedTypes": [place_type],
            "maxResultCount": 5,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_meters,
                }
            },
        }
        resp = requests.post(
            "https://places.googleapis.com/v1/places:searchNearby",
            headers=headers,
            json=body,
            timeout=10,
        )
        data = resp.json()
        results = []
        for place in data.get("places", []):
            results.append({
                "name": place.get("displayName", {}).get("text"),
                "address": place.get("formattedAddress"),
                "location": place.get("location"),
            })
        return results
    except Exception as e:
        return [{"error": f"Failed to find nearby places: {str(e)}"}]


def list_destinations(category: str = "") -> list[dict]:
    """Retrieve travel destinations from Firestore database.

    Args:
        category: Optional category filter (e.g. 'Cultural', 'Beach', 'Metropolitan', 'Nature & Adventure').

    Returns:
        List of destination dictionaries.
    """
    collection_ref = db.collection(COLLECTION_NAME)
    docs = collection_ref.stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        if not category or data.get("category", "").lower() == category.lower():
            results.append(data)
    return results


def get_destination_details(destination_id: str) -> dict:
    """Retrieve detailed travel information for a specific destination by its ID.

    Args:
        destination_id: The unique identifier of the destination (e.g. 'kyoto', 'paris', 'santorini', 'banff', 'tokyo').

    Returns:
        Dictionary containing destination details or an error message dict if not found.
    """
    doc_ref = db.collection(COLLECTION_NAME).document(destination_id.lower().strip())
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return {"error": f"Destination with ID '{destination_id}' not found."}


def add_destination(
    destination_id: str,
    name: str,
    country: str,
    category: str,
    avg_cost_per_day: int,
    best_season: str,
    description: str,
    highlights: list[str],
) -> str:
    """Add or update a travel destination in the Firestore database.

    Args:
        destination_id: Unique identifier for the destination (e.g., 'rome').
        name: Full name of the destination (e.g., 'Rome, Italy').
        country: Country where destination is located (e.g., 'Italy').
        category: Travel category (e.g., 'Cultural', 'Beach', 'Metropolitan', 'Nature & Adventure').
        avg_cost_per_day: Estimated average daily cost in USD.
        best_season: Recommended time of year to visit.
        description: A brief narrative description of the destination.
        highlights: List of top attractions or experiences.

    Returns:
        A success message string.
    """
    dest_data = {
        "destination_id": destination_id.lower().strip(),
        "name": name,
        "country": country,
        "category": category,
        "avg_cost_per_day": avg_cost_per_day,
        "best_season": best_season,
        "description": description,
        "highlights": highlights,
    }
    db.collection(COLLECTION_NAME).document(destination_id.lower().strip()).set(dest_data)
    return f"Successfully added destination '{name}' (ID: {destination_id}) to Firestore database."


def generate_destination_image(
    destination_id: str,
    visual_prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generate an AI visual image for a travel destination item using gemini-3.1-flash-lite-image in global region.

    Saves the image to session artifacts for Agent Playground, uploads image bytes directly to GCS, and returns public URL.

    Args:
        destination_id: Identifier of the destination item (e.g. 'kyoto', 'paris', 'santorini', 'banff', 'tokyo').
        visual_prompt: Descriptive visual scene to generate.
        tool_context: ADK ToolContext injected automatically by framework.

    Returns:
        Public HTTPS URL string of the uploaded Cloud Storage object (https://storage.googleapis.com/<bucket>/<object>).
    """
    try:
        genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=f"Generate a beautiful travel photo: {visual_prompt}",
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                if part.inline_data.mime_type:
                    mime_type = part.inline_data.mime_type
                break

        if not image_bytes:
            return "Failed to generate image content."

        ext = "png" if "png" in mime_type else "jpg"
        filename = f"{destination_id.lower().strip()}_{uuid.uuid4().hex[:6]}.{ext}"

        # 1. Save artifact so it shows up in Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload same image bytes directly to public GCS bucket (without writing to local file)
        object_name = f"destinations/{filename}"
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(object_name)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{object_name}"

        doc_ref = db.collection(COLLECTION_NAME).document(destination_id.lower().strip())
        if doc_ref.get().exists:
            doc_ref.update({"image_url": public_url})

        return public_url
    except Exception as e:
        return f"Error generating image: {str(e)}"


def generate_destination_video(
    destination_id: str,
    visual_prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generate a short video for a travel destination item using Google's Omni model (gemini-omni-flash-preview) in global region.

    Saves the video to session artifacts for Agent Playground, uploads video bytes directly to public GCS bucket, and returns public HTTPS URL.

    Args:
        destination_id: Identifier of the destination item (e.g. 'kyoto', 'paris', 'santorini', 'bali', 'tokyo').
        visual_prompt: Visual description of the short video scene to generate.
        tool_context: ADK ToolContext injected automatically by framework.

    Returns:
        Public HTTPS URL string of the uploaded Cloud Storage object (https://storage.googleapis.com/<bucket>/<object>).
    """
    try:
        genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"Generate a short video for travel destination {destination_id}: {visual_prompt}",
            response_modalities=["text", "video"],
        )

        video_bytes = None
        mime_type = "video/mp4"

        for out in getattr(interaction, "outputs", []):
            v = getattr(out, "video", None)
            if v:
                if getattr(v, "mime_type", None):
                    mime_type = v.mime_type
                if getattr(v, "bytes", None):
                    video_bytes = v.bytes
                    break
                elif getattr(v, "uri", None) and v.uri.startswith("gs://"):
                    parts = v.uri[5:].split("/", 1)
                    sc = storage.Client(project=PROJECT_ID)
                    blob = sc.bucket(parts[0]).blob(parts[1])
                    video_bytes = blob.download_as_bytes()
                    break

        if not video_bytes:
            return "Failed to generate video content."

        filename = f"{destination_id.lower().strip()}_{uuid.uuid4().hex[:6]}.mp4"

        # 1. Save artifact so it shows up in Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload same video bytes directly to public GCS bucket (without writing to local file)
        object_name = f"destinations/videos/{filename}"
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(object_name)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{object_name}"

        doc_ref = db.collection(COLLECTION_NAME).document(destination_id.lower().strip())
        if doc_ref.get().exists:
            doc_ref.update({"video_url": public_url})

        return public_url
    except Exception as e:
        return f"Error generating video: {str(e)}"


def get_real_weather(city: str) -> dict:
    """Fetch real-time live weather and climate data for any global city using the public Open-Meteo API.

    Args:
        city: City name to look up live weather for (e.g., 'Tokyo', 'Paris', 'Kyoto', 'Rome').

    Returns:
        Dictionary containing real-time weather information including temperature (°C & °F), wind speed, and timezone.
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if api_key:
        try:
            resp = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": api_key, "units": "metric"},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                temp_c = data["main"]["temp"]
                return {
                    "city": data.get("name", city),
                    "country": data.get("sys", {}).get("country"),
                    "temperature_celsius": round(temp_c, 1),
                    "temperature_fahrenheit": round(temp_c * 9 / 5 + 32, 1),
                    "condition": data["weather"][0]["description"],
                    "wind_speed_kmh": round(data["wind"]["speed"] * 3.6, 1),
                    "source": "OpenWeatherMap API",
                }
        except Exception:
            pass

    try:
        geo_resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=5,
        )
        geo_data = geo_resp.json()
        if not geo_data.get("results"):
            return {"error": f"City '{city}' not found."}

        loc = geo_data["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]

        weather_resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current_weather": True},
            timeout=5,
        )
        weather_data = weather_resp.json()
        current = weather_data.get("current_weather", {})
        temp_c = current.get("temperature", 0.0)

        return {
            "city": loc.get("name"),
            "country": loc.get("country"),
            "timezone": loc.get("timezone"),
            "temperature_celsius": temp_c,
            "temperature_fahrenheit": round(temp_c * 9 / 5 + 32, 1),
            "wind_speed_kmh": current.get("windspeed"),
            "source": "Open-Meteo Public API",
        }
    except Exception as e:
        return {"error": f"Failed to fetch live weather: {str(e)}"}


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


# Memory Bank Configuration
MEMORY_BANK_ID = "1389403915753095168"
os.environ.setdefault("GOOGLE_CLOUD_AGENT_ENGINE_ID", MEMORY_BANK_ID)


def memory_service_builder():
    """Build Vertex AI Memory Bank service for deployed container."""
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-central1",
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """Memory generation callback: extract and save durable memories after each turn."""
    await callback_context.add_session_to_memory()
    return None


# Load Agent Engine resource name from deployment_metadata.json if available
agent_engine_resource_name = None
metadata_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "deployment_metadata.json"
)
if os.path.exists(metadata_path):
    try:
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
            agent_engine_resource_name = metadata.get("remote_agent_runtime_id")
    except Exception:
        pass

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)


# A2UI Schema Manager Configuration (v0.8)
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are an expert Travel Concierge assistant. You remember the user's stated "
        "preferences, dietary constraints, and facts from previous conversations and use them to personalize your responses. "
        "You help travelers discover destinations, explore travel recommendations, check budgets, add new destinations, "
        "generate destination images, geocode addresses into coordinates, find nearby restaurants or attractions, "
        "look up real live weather or current time, and execute Python code safely in a sandbox using your tools."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        geocode_address,
        find_nearby_places,
        list_destinations,
        get_destination_details,
        add_destination,
        generate_destination_image,
        generate_destination_video,
        get_real_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
