import logging
from typing import Union, Dict
import struct
from .messages import NMEA2000Message, PGN


class MessageVerifier:
    """Verifies NMEA 2000 message structure and content"""

    @staticmethod
    def verify_can_frame(frame: bytes) -> Dict:
        """Verify complete NMEA 2000 frame."""
        if len(frame) < 5:
            raise ValueError(f"Frame too short: {len(frame)} bytes")

        # Get CAN ID from first 4 bytes (big endian)
        can_id = int.from_bytes(frame[0:4], "big")

        # Extract fields from CAN ID
        priority = (can_id >> 26) & 0x7
        pf = (can_id >> 16) & 0xFF
        ps = (can_id >> 8) & 0xFF
        source = can_id & 0xFF

        # Calculate PGN
        if pf < 240:  # PDU1 format
            pgn = pf << 8
        else:  # PDU2 format
            pgn = (pf << 8) | ps

        # Get data length and payload
        length = frame[4]
        data = frame[5 : 5 + length]

        return {
            "can_id": hex(can_id),
            "priority": priority,
            "pgn": pgn,
            "source": source,
            "length": length,
            "data": data.hex(),
        }

    @staticmethod
    def verify_position_data(data: bytes) -> Dict:
        """Verify Position Rapid Update (PGN 129025) data"""
        if len(data) != 8:
            raise ValueError(f"Invalid position data length: {len(data)}")

        lat, lon = struct.unpack("<II", data)

        # Convert from integer to degrees
        lat_deg = (lat if lat < 0x80000000 else lat - 0x100000000) / 1e7
        lon_deg = (lon if lon < 0x80000000 else lon - 0x100000000) / 1e7

        return {
            "latitude": lat_deg,
            "longitude": lon_deg,
            "raw_lat": hex(lat),
            "raw_lon": hex(lon),
        }

    @staticmethod
    def verify_cog_sog_data(data: bytes) -> Dict:
        """Verify COG & SOG Rapid Update (PGN 129026) data"""
        if len(data) != 8:
            raise ValueError(f"Invalid COG/SOG data length: {len(data)}")

        sid, ref, cog_raw, sog_raw = struct.unpack("<BBHH", data)

        # Convert to meaningful values
        cog_deg = (cog_raw / 10000) % 360
        sog_knots = sog_raw / 100

        return {
            "sid": sid,
            "reference": ref,
            "cog": cog_deg,
            "sog": sog_knots,
            "raw_cog": hex(cog_raw),
            "raw_sog": hex(sog_raw),
        }

    @staticmethod
    def verify_wind_data(data: bytes) -> Dict:
        """Verify Wind Data (PGN 130306) data"""
        if len(data) != 6:
            raise ValueError(f"Invalid wind data length: {len(data)}")

        sid, ref, speed, angle = struct.unpack("<BBhh", data)

        # Convert to meaningful values
        speed_ms = speed / 100  # 0.01 m/s resolution
        angle_deg = (angle / 10000) % 360  # 0.0001 radian resolution

        return {
            "sid": sid,
            "reference": ref,
            "speed": speed_ms,
            "angle": angle_deg,
            "raw_speed": hex(speed),
            "raw_angle": hex(angle),
        }


def verify_pgn_conversion(nmea_0183_message, converted_2000_message):
    """
    Verify that the converted NMEA 2000 message has the correct PGN
    and contains the expected data.
    """
    logging.debug(f"Original 0183 Message: {nmea_0183_message}")
    logging.debug(f"Converted 2000 PGN: {converted_2000_message.pgn}")
    logging.debug(f"PGN Description: {PGN.get_description(converted_2000_message.pgn)}")

    # Add more specific checks based on message type
    try:
        # Example for position messages
        if "lat" in nmea_0183_message and "lon" in nmea_0183_message:
            verifier = MessageVerifier()
            pos_data = verifier.verify_position_data(converted_2000_message.data)
            logging.debug(f"Converted Position: {pos_data}")
    except Exception as e:
        logging.error(f"Verification failed: {e}")


def log_verification_results(frame_info: Dict):
    """Helper function to log verification results in a readable format"""
    logging.debug("NMEA 2000 Frame Verification:")
    logging.debug(f"  CAN ID: {frame_info['can_id']}")
    logging.debug(f"  Priority: {frame_info['priority']}")
    logging.debug(f"  PGN: {frame_info['pgn']}")
    logging.debug(f"  Source: {frame_info['source']}")
    logging.debug(f"  Data Length: {frame_info['length']}")
    logging.debug(f"  Raw Data: {frame_info['data']}")

    # If additional PGN-specific data is present, log it
    for key, value in frame_info.items():
        if key not in ["can_id", "priority", "pgn", "source", "length", "data"]:
            logging.debug(f"  {key}: {value}")
