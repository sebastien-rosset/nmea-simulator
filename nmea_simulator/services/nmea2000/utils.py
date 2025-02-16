"""Utility functions for NMEA 2000 data conversion and handling."""

import math
from typing import Tuple

# Constants
KNOTS_TO_MS = 0.514444
RADIAN_SCALE = 65535 / (2 * math.pi)  # For converting radians to 16-bit unsigned
POSITION_SCALE = 1e7  # For lat/lon conversion (1e-7 degree resolution)


def encode_angle(degrees: float) -> int:
    """
    Encode an angle in degrees to NMEA 2000 16-bit unsigned integer.

    Args:
        degrees: Angle in degrees

    Returns:
        int: Encoded angle as 16-bit unsigned integer (0-65535)
    """
    # Normalize angle to 0-360
    normalized = degrees % 360
    # Convert to radians and scale to 16-bit range
    radians = math.radians(normalized)
    return int((radians / (2 * math.pi)) * 65535)


def decode_angle(raw: int) -> float:
    """
    Decode a NMEA 2000 16-bit unsigned integer to degrees.

    Args:
        raw: Encoded angle as 16-bit unsigned integer

    Returns:
        float: Angle in degrees (0-360)
    """
    radians = (raw / 65535.0) * 2 * math.pi
    return math.degrees(radians) % 360


def encode_speed_knots(knots: float) -> int:
    """
    Encode speed from knots to NMEA 2000 format (1/100th knot resolution).

    Args:
        knots: Speed in knots

    Returns:
        int: Encoded speed as unsigned integer
    """
    return int(round(knots * 100))


def decode_speed_knots(raw: int) -> float:
    """
    Decode NMEA 2000 speed to knots.

    Args:
        raw: Encoded speed

    Returns:
        float: Speed in knots
    """
    return round(raw / 100.0, 2)


def encode_wind_speed(knots: float) -> int:
    """
    Encode wind speed from knots to NMEA 2000 format (0.01 m/s resolution).

    Args:
        knots: Wind speed in knots

    Returns:
        int: Encoded wind speed
    """
    ms = round(knots * KNOTS_TO_MS, 3)  # Convert to m/s with 3 decimal precision
    return int(round(ms * 100))  # Convert to 0.01 m/s resolution


def decode_wind_speed(raw: int) -> float:
    """
    Decode NMEA 2000 wind speed to knots.

    Args:
        raw: Encoded wind speed

    Returns:
        float: Wind speed in knots
    """
    ms = round(raw / 100.0, 3)  # Convert to m/s with 3 decimal precision
    return round(ms / KNOTS_TO_MS, 1)  # Convert to knots with 1 decimal


def encode_position(degrees: float) -> int:
    """
    Encode position (latitude or longitude) to NMEA 2000 format.

    Args:
        degrees: Position in decimal degrees

    Returns:
        int: Encoded position as unsigned 32-bit integer
    """
    raw = int(degrees * POSITION_SCALE)
    if raw < 0:
        raw = raw + (1 << 32)  # Convert to unsigned 32-bit
    return raw & 0xFFFFFFFF


def decode_position(raw: int) -> float:
    """
    Decode NMEA 2000 position to decimal degrees.

    Args:
        raw: Encoded position

    Returns:
        float: Position in decimal degrees
    """
    if raw & (1 << 31):  # If highest bit is set (negative)
        raw = raw - (1 << 32)
    return raw / POSITION_SCALE


def encode_latlon(lat: float, lon: float) -> Tuple[int, int]:
    """
    Encode latitude and longitude to NMEA 2000 format.

    Args:
        lat: Latitude in decimal degrees (-90 to +90)
        lon: Longitude in decimal degrees (-180 to +180)

    Returns:
        Tuple[int, int]: Encoded latitude and longitude
    """
    lat = max(-90, min(90, lat))  # Clamp latitude to valid range
    lon = ((lon + 180) % 360) - 180  # Normalize longitude to -180/+180
    return encode_position(lat), encode_position(lon)


def decode_latlon(lat_raw: int, lon_raw: int) -> Tuple[float, float]:
    """
    Decode NMEA 2000 latitude and longitude.

    Args:
        lat_raw: Encoded latitude
        lon_raw: Encoded longitude

    Returns:
        Tuple[float, float]: Latitude and longitude in decimal degrees
    """
    lat = decode_position(lat_raw)
    lon = decode_position(lon_raw)
    return lat, lon
