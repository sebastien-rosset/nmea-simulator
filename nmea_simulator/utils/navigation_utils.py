from dataclasses import dataclass
import math
from typing import Dict, Tuple

from nmea_simulator.utils.coordinate_utils import calculate_bearing, calculate_distance
from .vessel_dynamics import (
    calculate_vessel_dynamics,
    update_rudder_angle,
    RudderState,
    VesselDynamics,
)


def update_vessel_position(
    current_position: Dict[str, float],
    rudder_state: RudderState,
    heading: float,
    desired_heading: float,
    speed: float,
    current_speed: float,
    current_direction: float,
    delta_time: float,
) -> Tuple[Dict[str, float], float, float, float]:
    """
    Update vessel position based on heading and speed, accounting for:
    - Rudder angle effect on heading
    - Water current
    - Speed through water

    Args:
        current_position: Dict with 'lat' and 'lon' keys in decimal degrees
        rudder_state: Current rudder configuration and angles
        heading: Vessel heading in degrees true
        desired_heading: Desired heading in degrees true
        speed: Vessel speed in knots
        current_speed: Water current speed in knots
        current_direction: Direction current is flowing TOWARDS in degrees true
        delta_time: Time elapsed since last update in seconds

    Returns:
        Tuple[Dict[str, float], float, float, float]:
            (Updated position, new COG, new heading, new rudder angle)
    """
    if delta_time < 0.001:  # Less than 1ms
        return current_position, heading, heading, rudder_state.starboard_angle

    # Update rudder angle based on desired heading
    new_rudder = update_rudder_angle(
        rudder_state.starboard_angle,
        desired_heading,
        heading,
        rudder_state.max_angle,
        delta_time,
    )

    # Calculate new heading based on rudder
    dynamics = calculate_vessel_dynamics(
        heading, new_rudder, rudder_state.max_angle, delta_time
    )
    new_heading = dynamics.heading

    # Convert speeds to meters per second
    speed_ms = speed * 0.514444  # Convert knots to m/s
    current_speed_ms = current_speed * 0.514444

    # Convert angles to radians
    heading_rad = math.radians(new_heading)
    current_dir_rad = math.radians(current_direction)

    # Calculate ship movement vector based on actual heading
    ship_dx = speed_ms * math.sin(heading_rad)
    ship_dy = speed_ms * math.cos(heading_rad)

    # Calculate current vector
    current_dx = current_speed_ms * math.sin(current_dir_rad)
    current_dy = current_speed_ms * math.cos(current_dir_rad)

    # Combined movement vector (ship + current)
    total_dx = (ship_dx - current_dx) * delta_time
    total_dy = (ship_dy - current_dy) * delta_time

    # Convert to angular distances
    R = 6371000  # Earth radius in meters
    lat_rad = math.radians(current_position["lat"])

    # Calculate position changes
    dlat = math.degrees(total_dy / R)
    dlon = math.degrees(total_dx / (R * math.cos(lat_rad)))

    # Create new position
    new_position = {
        "lat": current_position["lat"] + dlat,
        "lon": current_position["lon"] + dlon,
    }

    # Normalize coordinates
    new_position["lat"] = max(-90, min(90, new_position["lat"]))
    new_position["lon"] = ((new_position["lon"] + 180) % 360) - 180

    # Calculate actual COG from movement vector
    total_dx_per_second = total_dx / delta_time
    total_dy_per_second = total_dy / delta_time
    new_cog = math.degrees(math.atan2(total_dx_per_second, total_dy_per_second)) % 360

    return new_position, new_cog, new_heading, new_rudder


def calculate_vmg(speed: float, course: float, destination_bearing: float) -> float:
    """
    Calculate Velocity Made Good towards a destination.

    Args:
        speed: Vessel speed in knots
        course: Vessel course in degrees true
        destination_bearing: Bearing to destination in degrees true

    Returns:
        float: VMG in knots (positive towards destination, negative away)
    """
    # VMG = SOG * cos(COG - BRG)
    angle_diff = math.radians(abs(course - destination_bearing))
    return speed * math.cos(angle_diff)


@dataclass
class WaterSpeedVector:
    """Water speed calculation results"""

    speed: float  # Speed through water in knots
    direction: float  # Direction through water in degrees true


def calculate_water_speed(
    sog: float, cog: float, current_speed: float, current_direction: float
) -> WaterSpeedVector:
    """
    Calculate speed through water based on SOG and current.
    Uses vector addition of vessel movement and water current.

    Args:
        sog: Speed over ground in knots
        cog: Course over ground in degrees true
        current_speed: Water current speed in knots
        current_direction: Direction current is flowing TOWARDS in degrees true

    Returns:
        WaterSpeedVector: Speed and direction through water
    """
    # Convert angles to radians
    vessel_dir_rad = math.radians(cog)
    current_dir_rad = math.radians(current_direction)

    # Convert speeds and directions to vectors
    # Vessel vector (SOG)
    vx = sog * math.sin(vessel_dir_rad)
    vy = sog * math.cos(vessel_dir_rad)

    # Current vector
    cx = current_speed * math.sin(current_dir_rad)
    cy = current_speed * math.cos(current_dir_rad)

    # Subtract current vector to get water speed vector
    wx = vx - cx
    wy = vy - cy

    # Calculate water speed magnitude
    speed = math.sqrt(wx * wx + wy * wy)

    # Calculate direction through water
    direction = math.degrees(math.atan2(wx, wy)) % 360

    return WaterSpeedVector(speed, direction)


def calculate_course_to_position(
    current_lat: float, current_lon: float, target_lat: float, target_lon: float
) -> Tuple[float, float]:
    """
    Calculate course and distance to a target position.

    Args:
        current_lat: Current latitude in decimal degrees
        current_lon: Current longitude in decimal degrees
        target_lat: Target latitude in decimal degrees
        target_lon: Target longitude in decimal degrees

    Returns:
        Tuple[float, float]: (bearing in degrees true, distance in nautical miles)
    """
    distance = calculate_distance(current_lat, current_lon, target_lat, target_lon)

    bearing = calculate_bearing(current_lat, current_lon, target_lat, target_lon)

    return bearing, distance
