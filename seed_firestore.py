"""Seed script to populate Firestore with sample Travel Concierge destinations.

Uses hardcoded project ID 'qwiklabs-gcp-01-f3f508531c62' to ensure compatibility
when running locally and when deployed on Agent Platform.
"""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-01-f3f508531c62"
COLLECTION_NAME = "destinations"

SEED_DESTINATIONS = [
    {
        "destination_id": "kyoto",
        "name": "Kyoto, Japan",
        "country": "Japan",
        "category": "Cultural",
        "avg_cost_per_day": 180,
        "best_season": "Spring & Autumn",
        "description": "Historic city known for classical temples, gardens, imperial palaces, and traditional tea houses.",
        "highlights": ["Fushimi Inari Shrine", "Arashiyama Bamboo Grove", "Gion District"],
    },
    {
        "destination_id": "paris",
        "name": "Paris, France",
        "country": "France",
        "category": "Metropolitan",
        "avg_cost_per_day": 250,
        "best_season": "Spring & Summer",
        "description": "The City of Light, world-famous for art, fashion, gastronomy, and iconic architectural landmarks.",
        "highlights": ["Eiffel Tower", "Louvre Museum", "Montmartre"],
    },
    {
        "destination_id": "santorini",
        "name": "Santorini, Greece",
        "country": "Greece",
        "category": "Beach",
        "avg_cost_per_day": 300,
        "best_season": "Summer & Early Autumn",
        "description": "Iconic Aegean island renowned for whitewashed cliffside villages, dramatic caldera views, and volcanic beaches.",
        "highlights": ["Oia Sunset Viewpoint", "Red Beach", "Akrotiri Archaeological Site"],
    },
    {
        "destination_id": "banff",
        "name": "Banff, Canada",
        "country": "Canada",
        "category": "Nature & Adventure",
        "avg_cost_per_day": 210,
        "best_season": "Winter & Summer",
        "description": "Breathtaking national park featuring turquoise glacial lakes, snow-capped peaks, and rich wildlife.",
        "highlights": ["Lake Louise", "Moraine Lake", "Banff Upper Hot Springs"],
    },
    {
        "destination_id": "tokyo",
        "name": "Tokyo, Japan",
        "country": "Japan",
        "category": "Metropolitan",
        "avg_cost_per_day": 200,
        "best_season": "Spring & Autumn",
        "description": "Vibrant megacity seamlessly blending futuristic neon skyscrapers with ancient historic temples.",
        "highlights": ["Shinjuku Crossing", "Senso-ji Temple", "Akihabara Electric Town"],
    },
]


def seed_database():
    db = firestore.Client(project=PROJECT_ID)
    print(f"Connected to Firestore in project: {PROJECT_ID}")
    
    collection_ref = db.collection(COLLECTION_NAME)
    for dest in SEED_DESTINATIONS:
        doc_id = dest["destination_id"]
        collection_ref.document(doc_id).set(dest)
        print(f"Seeded destination: {dest['name']} (ID: {doc_id})")

    print(f"Successfully seeded {len(SEED_DESTINATIONS)} destinations into collection '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    seed_database()
