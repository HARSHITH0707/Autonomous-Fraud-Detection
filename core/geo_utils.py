import logging
from datetime import datetime, timezone
from typing import Tuple, Optional

import httpx
from geopy.distance import geodesic

log = logging.getLogger(__name__)

# Country centroid coordinates (Approximate)
COUNTRY_COORDS = {
    "IN": (20.5937, 78.9629),    # India
    "AE": (23.4241, 53.8478),    # UAE
    "US": (37.0902, -95.7129),   # USA
    "GB": (55.3781, -3.4360),    # UK
    "NG": (9.0820, 8.6753),      # Nigeria
    "CN": (35.8617, 104.1954),   # China
    "RU": (61.5240, 105.3188),   # Russia
    "BR": (-14.2350, -51.9253),  # Brazil
    "DE": (51.1657, 10.4515),    # Germany
    "FR": (46.2276, 2.2137),     # France
    "JP": (36.2048, 138.2529),   # Japan
    "AU": (-25.2744, 133.7751),  # Australia
    "CA": (56.1304, -106.3468),  # Canada
    "SG": (1.3521, 103.8198),    # Singapore
}

async def get_ip_location(ip_address: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Look up the exact coordinates of an IP address using an external API.
    This calculates the current location so we can differentiate exact locations 
    rather than relying solely on country centroids.
    """
    if not ip_address or ip_address.startswith("10.") or ip_address.startswith("192.168.") or ip_address.startswith("127."):
        return None, None
    
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"http://ip-api.com/json/{ip_address}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    return data.get("lat"), data.get("lon")
    except Exception as e:
        log.warning(f"Failed to geolocate IP {ip_address}: {e}")
    return None, None

def _ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC-aware. Treats naive datetimes as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def calculate_travel_velocity(
    prev_lat: float, prev_lng: float, prev_time: datetime,
    curr_lat: float, curr_lng: float, curr_time: datetime
) -> Tuple[float, float]:
    """
    Calculates distance (km) and velocity (km/h) between two logins using geopy.
    Returns (0.0, 0.0) if coordinates are the same.
    """
    if (prev_lat, prev_lng) == (curr_lat, curr_lng) or prev_lat == 0.0 or curr_lat == 0.0:
        return 0.0, 0.0
    
    prev_time = _ensure_utc(prev_time)
    curr_time = _ensure_utc(curr_time)
    
    dist = geodesic((prev_lat, prev_lng), (curr_lat, curr_lng)).kilometers
    time_diff = (curr_time - prev_time).total_seconds() / 3600.0 # hours
    
    if time_diff <= 0:
        return dist, 9999.0 # Instant travel
        
    velocity = dist / time_diff
    return dist, velocity

def is_impossible_travel(velocity_kmh: float, threshold: float = 900.0) -> bool:
    """
    Checks if the velocity exceeds standard commercial flight speed (~900 km/h).
    """
    return velocity_kmh > threshold
