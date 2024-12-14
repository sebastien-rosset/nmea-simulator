import math
from dataclasses import dataclass
from typing import Tuple

@dataclass
class WindData:
    """Container for wind calculation results"""
    apparent_speed: float  # knots
    apparent_angle: float  # degrees relative to bow (-180 to +180)

def calculate_apparent_wind(true_wind_speed: float, true_wind_direction: float,
                          vessel_speed: float, vessel_heading: float) -> WindData:
    """
    Calculate apparent wind based on true wind and vessel movement.
    Uses vector mathematics to combine true wind and vessel motion.
    
    Args:
        true_wind_speed: Wind speed in knots
        true_wind_direction: Direction wind is coming FROM in degrees true
        vessel_speed: Vessel speed in knots
        vessel_heading: Vessel heading in degrees true

    Returns:
        WindData: Contains apparent wind speed and angle
    """
    # Convert angles to radians
    true_wind_dir_rad = math.radians(true_wind_direction)
    vessel_heading_rad = math.radians(vessel_heading)

    # Convert true wind to vector components
    true_wind_x = true_wind_speed * math.sin(true_wind_dir_rad)
    true_wind_y = true_wind_speed * math.cos(true_wind_dir_rad)

    # Convert vessel motion to vector components
    vessel_x = vessel_speed * math.sin(vessel_heading_rad)
    vessel_y = vessel_speed * math.cos(vessel_heading_rad)

    # Calculate apparent wind components by subtracting vessel motion
    apparent_x = true_wind_x - vessel_x
    apparent_y = true_wind_y - vessel_y

    # Calculate apparent wind speed
    apparent_speed = math.sqrt(apparent_x**2 + apparent_y**2)

    # Calculate apparent wind angle relative to vessel heading
    apparent_angle_rad = math.atan2(apparent_x, apparent_y) - vessel_heading_rad

    # Convert to degrees and normalize to -180 to +180
    apparent_angle = math.degrees(apparent_angle_rad)
    if apparent_angle > 180:
        apparent_angle -= 360
    elif apparent_angle < -180:
        apparent_angle += 360

    return WindData(apparent_speed, apparent_angle)
