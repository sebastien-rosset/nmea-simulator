import math
import re
from typing import Tuple, Union

def parse_coordinate(coord: Union[str, float, int]) -> float:
    """
    Parse coordinate string in various formats or return numeric value.
    Supports:
    - Decimal degrees (123.456)
    - Degrees decimal minutes ("37° 40.3574' N" or "37 40.3574 N")
    - Basic directional ("122° W" or "122 W")

    Args:
        coord: Coordinate as string or number

    Returns:
        float: Decimal degrees (negative for West/South)
    """
    if isinstance(coord, (float, int)):
        return float(coord)

    # Remove special characters and extra spaces
    clean_coord = coord.replace("°", " ").replace("'", " ").replace('"', " ")
    clean_coord = " ".join(clean_coord.split())

    # Try to parse different formats
    try:
        # Check for directional format first
        match = re.match(r"^(-?\d+\.?\d*)\s*([NSEW])$", clean_coord)
        if match:
            value = float(match.group(1))
            direction = match.group(2)
            return -value if direction in ["W", "S"] else value

        # Check for degrees decimal minutes format
        match = re.match(r"^(-?\d+)\s+(\d+\.?\d*)\s*([NSEW])$", clean_coord)
        if match:
            degrees = float(match.group(1))
            minutes = float(match.group(2))
            direction = match.group(3)
            value = degrees + minutes / 60
            return -value if direction in ["W", "S"] else value

        # Try simple float conversion
        return float(clean_coord)

    except (ValueError, AttributeError) as e:
        raise ValueError(f"Unable to parse coordinate: {coord}") from e
    
def calculate_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculate distance between two points in nautical miles"""
    R = 3440.065  # Earth's radius in nautical miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_bearing(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculate true bearing between two points"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(
        lat2
    ) * math.cos(dlon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360

def calculate_cross_track_error(current_lat: float, current_lon: float, 
                              start_lat: float, start_lon: float,
                              end_lat: float, end_lon: float) -> Tuple[float, str]:
    """
    Calculate cross track error between current position and route leg.
    Assumes valid input coordinates - validation should be done before calling.
    
    Args:
        current_lat: Current position latitude in decimal degrees
        current_lon: Current position longitude in decimal degrees
        start_lat: Route start point latitude in decimal degrees
        start_lon: Route start point longitude in decimal degrees
        end_lat: Route end point latitude in decimal degrees
        end_lon: Route end point longitude in decimal degrees

    Returns:
        Tuple[float, str]: (XTE magnitude in nautical miles, direction to steer 'L' or 'R')
    """
    # Convert to radians for calculations
    lat1, lon1 = map(math.radians, [start_lat, start_lon])
    lat2, lon2 = map(math.radians, [end_lat, end_lon])
    lat3, lon3 = map(math.radians, [current_lat, current_lon])

    # Calculate distances and bearings
    try:
        # Calculate initial bearing from start to current position
        y = math.sin(lon3 - lon1) * math.cos(lat3)
        x = math.cos(lat1) * math.sin(lat3) - math.sin(lat1) * math.cos(
            lat3
        ) * math.cos(lon3 - lon1)
        bearing13 = math.atan2(y, x)

        # Calculate initial bearing from start to end waypoint
        y = math.sin(lon2 - lon1) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(
            lat2
        ) * math.cos(lon2 - lon1)
        bearing12 = math.atan2(y, x)

        # Calculate distance from start to current position
        d13 = math.acos(
            math.sin(lat1) * math.sin(lat3)
            + math.cos(lat1) * math.cos(lat3) * math.cos(lon3 - lon1)
        )

        # Convert to nautical miles
        R = 3440.065  # Earth's radius in nautical miles
        xte = abs(math.asin(math.sin(d13) * math.sin(bearing13 - bearing12)) * R)

        # Determine direction to steer
        cross_prod = math.sin(lon2 - lon1) * math.cos(lat2) * (
            math.sin(lat3) - math.sin(lat1)
        ) - math.sin(lat2 - lat1) * (math.sin(lon3 - lon1) * math.cos(lat3))

        direction = "L" if cross_prod < 0 else "R"

    except (ValueError, ZeroDivisionError):
        # If we get any math errors, assume no cross track error
        xte = 0.0
        direction = "L"

    return xte, direction