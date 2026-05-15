from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from typing import Tuple, Optional

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

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians 
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula 
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371 # Radius of earth in kilometers.
    return c * r

def calculate_travel_velocity(
    prev_country: str, prev_time: datetime,
    curr_country: str, curr_time: datetime
) -> Tuple[float, float]:
    """
    Calculates distance (km) and velocity (km/h) between two logins.
    Returns (0.0, 0.0) if countries are the same or coordinates unknown.
    """
    if prev_country == curr_country:
        return 0.0, 0.0
    
    p_coords = COUNTRY_COORDS.get(prev_country)
    c_coords = COUNTRY_COORDS.get(curr_country)
    
    if not p_coords or not c_coords:
        return 0.0, 0.0
    
    dist = haversine_km(p_coords[0], p_coords[1], c_coords[0], c_coords[1])
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
