# src/services/nmea2000/converter.py
import struct
from datetime import datetime
from typing import List, Optional

from .messages import NMEA2000Message
from .pgns import PGN


class NMEA2000Converter:
    """Converts NMEA 0183 messages to NMEA 2000 format"""

    @staticmethod
    def convert_rmc_to_2000(message: str) -> List[NMEA2000Message]:
        """
        Convert RMC message to NMEA 2000 messages.
        Creates multiple PGNs: Position, COG/SOG
        """
        # Parse RMC fields
        fields = message.split(",")
        if len(fields) < 12:
            raise ValueError("Invalid RMC message")

        try:
            time = fields[1]
            lat = float(fields[3]) if fields[3] else 0.0
            lat_dir = fields[4]
            lon = float(fields[5]) if fields[5] else 0.0
            lon_dir = fields[6]
            sog = float(fields[7]) if fields[7] else 0.0
            cog = float(fields[8]) if fields[8] else 0.0

            # Convert lat/lon to signed degrees
            lat = -lat if lat_dir == "S" else lat
            lon = -lon if lon_dir == "W" else lon

            messages = []

            # Position Rapid Update (129025)
            position_data = struct.pack(
                "<ll",
                int(lat * 1e7),  # Latitude in 1e-7 degrees
                int(lon * 1e7),  # Longitude in 1e-7 degrees
            )
            messages.append(
                NMEA2000Message(
                    pgn=PGN.POSITION_RAPID,
                    priority=2,
                    source=0,
                    destination=255,
                    data=position_data,
                )
            )

            # COG/SOG Rapid Update (129026)
            cog_sog_data = struct.pack(
                "<BBHH",
                0xFF,  # SID (not used)
                0,  # COG Reference (true)
                int(cog * 10000),  # COG in 10000th of a degree
                int(sog * 100),  # SOG in 100th of a knot
            )
            messages.append(
                NMEA2000Message(
                    pgn=PGN.COG_SOG_RAPID,
                    priority=2,
                    source=0,
                    destination=255,
                    data=cog_sog_data,
                )
            )

            return messages

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting RMC: {e}")

    @staticmethod
    def convert_gga_to_2000(message: str) -> NMEA2000Message:
        """
        Convert GGA message to NMEA 2000 GNSS Position Data (PGN 129029)
        """
        fields = message.split(",")
        if len(fields) < 14:
            raise ValueError("Invalid GGA message")

        try:
            time = fields[1]
            lat = float(fields[2]) if fields[2] else 0.0
            lat_dir = fields[3]
            lon = float(fields[4]) if fields[4] else 0.0
            lon_dir = fields[5]
            quality = int(fields[6]) if fields[6] else 0
            satellites = int(fields[7]) if fields[7] else 0
            hdop = float(fields[8]) if fields[8] else 0.0
            altitude = float(fields[9]) if fields[9] else 0.0

            # Convert lat/lon to signed degrees
            lat = -lat if lat_dir == "S" else lat
            lon = -lon if lon_dir == "W" else lon

            # Pack GNSS data
            data = struct.pack(
                "<BBHLlllHHBB",
                0xFF,  # SID (not used)
                0xFF,  # Days since 1970 (not used)
                0,  # Seconds since midnight
                int(lat * 1e7),  # Latitude
                int(lon * 1e7),  # Longitude
                int(altitude * 100),  # Altitude in centimeters
                0,  # GNSS type
                quality,  # Method/Quality
                satellites,  # Number of satellites
                int(hdop * 100),  # HDOP
                0xFF,  # Reserved
            )

            return NMEA2000Message(
                pgn=PGN.GNSS_POSITION, priority=2, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting GGA: {e}")

    @staticmethod
    def convert_dbt_to_2000(message: str) -> NMEA2000Message:
        """
        Convert DBT message to NMEA 2000 Water Depth (PGN 128267)
        """
        fields = message.split(",")
        if len(fields) < 6:
            raise ValueError("Invalid DBT message")

        try:
            # Use meters field
            depth = float(fields[3]) if fields[3] else 0.0

            # Pack depth data
            data = struct.pack(
                "<BLhH",
                0xFF,  # SID (not used)
                int(depth * 100),  # Depth in centimeters
                0,  # Offset (0 = depth below transducer)
                0xFFFF,  # Maximum range scale (not used)
            )

            return NMEA2000Message(
                pgn=PGN.WATER_DEPTH, priority=3, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting DBT: {e}")

    @staticmethod
    def convert_mwv_to_2000(message: str, is_true: bool) -> NMEA2000Message:
        """
        Convert MWV message to NMEA 2000 Wind Data (PGN 130306)
        """
        fields = message.split(",")
        if len(fields) < 5:
            raise ValueError("Invalid MWV message")

        try:
            wind_angle = float(fields[1]) if fields[1] else 0.0
            wind_speed = float(fields[3]) if fields[3] else 0.0

            # Reference: 0=true, 2=apparent
            reference = 0 if is_true else 2

            # Pack wind data
            data = struct.pack(
                "<BBHHH",
                0xFF,  # SID (not used)
                reference,  # Wind reference
                int(wind_speed * 100),  # Wind speed in 0.01 m/s
                int(wind_angle * 10000),  # Wind angle in 10000th of a degree
                0xFFFF,  # Reserved
            )

            return NMEA2000Message(
                pgn=PGN.WIND_DATA, priority=2, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting MWV: {e}")

    @staticmethod
    def convert_xte_to_2000(message: str) -> NMEA2000Message:
        """
        Convert XTE message to NMEA 2000 Cross Track Error (PGN 129283)
        """
        fields = message.split(",")
        if len(fields) < 5:
            raise ValueError("Invalid XTE message")

        try:
            magnitude = float(fields[2]) if fields[2] else 0.0
            direction = fields[3]  # L or R

            # Direction multiplier: -1 for Left, 1 for Right
            multiplier = 1 if direction == "R" else -1
            xte = magnitude * multiplier

            # Pack XTE data
            data = struct.pack(
                "<BBBll",
                0xFF,  # SID (not used)
                0xFF,  # XTE mode (not used)
                0,  # Navigation terminated
                int(xte * 100),  # XTE in meters
                0,  # Reserved
            )

            return NMEA2000Message(
                pgn=PGN.XTE, priority=3, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting XTE: {e}")
