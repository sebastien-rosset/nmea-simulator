# src/services/nmea2000/converter.py
import math
import struct
from datetime import datetime
import logging
from typing import List, Optional
from math import floor

from .messages import NMEA2000Message
from .pgns import PGN


class NMEA2000Converter:
    """Converts NMEA 0183 messages to NMEA 2000 format"""

    def _parse_lat_lon(
        self, lat_str: str, lat_dir: str, lon_str: str, lon_dir: str
    ) -> tuple:
        """Helper to parse NMEA 0183 lat/lon format"""
        try:
            # Convert DDMM.MMM to decimal degrees
            lat_deg = floor(float(lat_str) / 100)
            lat_min = float(lat_str) - (lat_deg * 100)
            lat = lat_deg + (lat_min / 60)
            if lat_dir == "S":
                lat = -lat

            lon_deg = floor(float(lon_str) / 100)
            lon_min = float(lon_str) - (lon_deg * 100)
            lon = lon_deg + (lon_min / 60)
            if lon_dir == "W":
                lon = -lon

            return lat, lon
        except (ValueError, TypeError):
            return 0.0, 0.0

    def _get_message_type(self, message: str) -> str:
        """Extract message type without talker ID from NMEA 0183 message"""
        if not message:
            return ""

        # Handle messages with or without $ prefix
        msg = message[1:] if message.startswith("$") else message

        # Split on comma and get sentence identifier
        parts = msg.split(",")[0]

        # Get everything after the talker ID (which is 2 characters)
        if len(parts) > 2:
            return parts[2:]

        return ""

    def convert_rmc_to_2000(self, message: str) -> List[NMEA2000Message]:
        """Convert RMC message to NMEA 2000 messages."""
        messages = []
        logging.debug(f"Converting RMC message: {message}")
        fields = message.split(",")
        if len(fields) < 12:
            logging.warning(f"RMC message has insufficient fields: {len(fields)}")
            return messages

        try:
            # Parse time
            time_str = fields[1]
            hour = int(time_str[0:2])
            minute = int(time_str[2:4])
            second = int(time_str[4:6])

            # Parse date
            date_str = fields[9]
            day = int(date_str[0:2])
            month = int(date_str[2:4])
            year = 2000 + int(date_str[4:6])  # Assuming 20xx

            # Parse position
            lat, lon = self._parse_lat_lon(fields[3], fields[4], fields[5], fields[6])

            # Clamp latitude to valid range and convert to unsigned integer
            lat = max(-90, min(90, lat))
            lat_int = int((lat * 1e7) % 4294967296)  # Handle unsigned 32-bit wraparound

            # Handle longitude wraparound and convert to unsigned integer
            lon = ((lon + 180) % 360) - 180
            lon_int = int((lon * 1e7) % 4294967296)  # Handle unsigned 32-bit wraparound

            # Parse speed and course
            sog = float(fields[7]) if fields[7] else 0.0
            cog = float(fields[8]) if fields[8] else 0.0

            # System Time (PGN 126992)
            dt = datetime(year, month, day)
            epoch = datetime(1970, 1, 1)
            days_since_epoch = (dt - epoch).days
            msecs = (hour * 3600 + minute * 60 + second) * 1000

            time_data = struct.pack(
                "<BBHIh",
                0xFF,  # SID (not used)
                0,  # Time Source (0 = GPS)
                days_since_epoch,
                msecs,  # Milliseconds since midnight
                0,  # Reserved
            )
            logging.debug(
                f"System Time data: {year}-{month}-{day} {hour}:{minute}:{second}. SOG={sog}kts, COG={cog}°. position: lat={lat}, lon={lon}"
            )
            messages.append(
                NMEA2000Message(
                    pgn=PGN.SYSTEM_TIME,
                    priority=3,
                    source=0,
                    destination=255,
                    data=time_data,
                )
            )

            # Position Rapid Update (PGN 129025)
            pos_data = struct.pack(
                "<II",  # Use unsigned integers for lat/lon
                lat_int,  # Latitude in 1e-7 degrees
                lon_int,  # Longitude in 1e-7 degrees
            )

            messages.append(
                NMEA2000Message(
                    pgn=PGN.POSITION_RAPID,
                    priority=2,
                    source=0,
                    destination=255,
                    data=pos_data,
                )
            )

            # COG & SOG, Rapid Update (PGN 129026)
            # Convert COG to radians (NMEA 2000 PGN 129026 uses radians)
            cog_rad = (cog * math.pi / 180.0) % (2 * math.pi)
            cog_int = int(cog_rad * 10000)  # Scale to 1/10000th radian

            # Convert SOG from knots to 1/100th m/s
            # 1 knot = 0.514444 m/s
            sog_ms100 = int(sog * 0.514444 * 100)  # Scale to 0.01 m/s

            cog_sog_data = struct.pack(
                "<BBHH",
                0xFF,  # SID (not used)
                0,  # COG Reference (0 = True)
                cog_int,  # COG in 1/10000th radian
                sog_ms100,  # SOG in 0.01 m/s
            )
            cog_sog_msg = NMEA2000Message(
                pgn=PGN.COG_SOG_RAPID,
                priority=2,
                source=0,
                destination=255,
                data=cog_sog_data,
            )
            messages.append(cog_sog_msg)
            logging.debug(f"COG: {cog}° -> {cog_rad:.4f} rad -> {cog_int} (scaled)")
            logging.debug(f"SOG: {sog} knots -> {sog_ms100} 0.01 m/s")
            logging.debug(f"COG/SOG raw data: {cog_sog_data.hex()}")

            return messages

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting RMC: {e}")

    def _create_system_time_message(
        self, year: int, month: int, day: int, hour: int, minute: int, second: int
    ) -> NMEA2000Message:
        """Create System Time message (PGN 126992)"""
        # Calculate days since Unix epoch
        dt = datetime(year, month, day)
        epoch = datetime(1970, 1, 1)
        days_since_epoch = (dt - epoch).days

        # Calculate seconds since midnight
        seconds = hour * 3600 + minute * 60 + second

        data = struct.pack(
            "<BBHHI",
            0xFF,  # SID (not used)
            0,  # Time Source (0 = GPS)
            days_since_epoch,
            seconds * 10000,  # Milliseconds since midnight
            0,  # Reserved
        )

        return NMEA2000Message(
            pgn=PGN.SYSTEM_TIME, priority=3, source=0, destination=255, data=data
        )

    def _create_position_message(self, lat: float, lon: float) -> NMEA2000Message:
        """Create Position Rapid Update message (PGN 129025)"""
        data = struct.pack(
            "<ll",
            int(lat * 1e7),  # Latitude in 1e-7 degrees
            int(lon * 1e7),  # Longitude in 1e-7 degrees
        )

        return NMEA2000Message(
            pgn=PGN.POSITION_RAPID, priority=2, source=0, destination=255, data=data
        )

    def _create_cog_sog_message(self, cog: float, sog: float) -> NMEA2000Message:
        """Create COG & SOG Rapid Update message (PGN 129026)"""
        data = struct.pack(
            "<BBHH",
            0xFF,  # SID (not used)
            0,  # COG Reference (0 = True)
            int(cog * 10000),  # COG in 10000th of a degree
            int(sog * 100),  # SOG in 100th of a knot
        )

        return NMEA2000Message(
            pgn=PGN.COG_SOG_RAPID, priority=2, source=0, destination=255, data=data
        )

    def convert_gga_to_2000(self, message: str) -> NMEA2000Message:
        """Convert GGA message to NMEA 2000 GNSS Position Data (PGN 129029)"""
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

            # Convert DDMM.MMM to decimal degrees
            lat_deg = floor(lat / 100)
            lat_min = lat - (lat_deg * 100)
            lat = lat_deg + (lat_min / 60)
            if lat_dir == "S":
                lat = -lat

            lon_deg = floor(lon / 100)
            lon_min = lon - (lon_deg * 100)
            lon = lon_deg + (lon_min / 60)
            if lon_dir == "W":
                lon = -lon

            # Pack GNSS data using proper integer types
            # Use q (long long) for larger lat/lon values
            data = struct.pack(
                "<BBHqqiHBBB",
                0xFF,  # SID (not used)
                0xFF,  # Days since 1970 (not used)
                0,  # Time of position (seconds since midnight)
                int(lat * 1e7),  # Latitude
                int(lon * 1e7),  # Longitude
                int(altitude * 100),  # Altitude in centimeters
                satellites & 0xFFFF,  # Number of SVs
                quality & 0xFF,  # Method/Quality
                int(hdop * 100) & 0xFF,  # HDOP
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

            # Convert to 0.01m units
            depth_value = int(depth * 100)

            # Pack bytes manually to ensure correct order
            data = bytes(
                [
                    0xFF,  # SID
                    0x00,  # Source type
                    depth_value & 0xFF,  # Depth byte 0
                    (depth_value >> 8) & 0xFF,  # Depth byte 1
                    (depth_value >> 16) & 0xFF,  # Depth byte 2
                    (depth_value >> 24) & 0xFF,  # Depth byte 3
                    0x00,  # Offset LSB
                    0x00,  # Offset MSB
                ]
            )

            logging.debug(f"Converting depth {depth}m to raw value {depth_value}")
            logging.debug(f"Raw data bytes: {' '.join([f'{b:02X}' for b in data])}")

            return NMEA2000Message(
                pgn=PGN.WATER_DEPTH, priority=3, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting DBT: {e}")

    def convert_mwv_to_2000(self, message: str, is_true: bool) -> NMEA2000Message:
        """Convert MWV message to NMEA 2000 Wind Data (PGN 130306)"""
        fields = message.split(",")
        if len(fields) < 5:
            raise ValueError("Invalid MWV message")

        try:
            wind_angle = float(fields[1]) if fields[1] else 0.0
            wind_speed = float(fields[3]) if fields[3] else 0.0

            # Convert wind speed from knots to m/s (1 knot = 0.514444 m/s)
            wind_speed_ms = wind_speed * 0.514444

            # Reference: 0=true, 2=apparent
            reference = 0 if is_true else 2

            # Pack wind data using unsigned short (H) for angle and speed
            data = struct.pack(
                "<BBHHh",
                0xFF,  # SID (not used)
                reference,  # Wind reference
                int(wind_speed_ms * 100) & 0xFFFF,  # Wind speed in 0.01 m/s
                int(wind_angle * 10000) & 0xFFFF,  # Wind angle in 1/10000th of a degree
                0,  # Reserved
            )

            return NMEA2000Message(
                pgn=PGN.WIND_DATA, priority=2, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting MWV: {e}")

    def convert_xte_to_2000(self, message: str) -> NMEA2000Message:
        """
        Convert XTE message to NMEA 2000 Cross Track Error (PGN 129283)
        Format: $--XTE,A,A,x.x,a,N,a*hh
            1,2,3,4,5,6
        1,2: Status fields (A = valid)
        3: Cross track error magnitude
        4: Direction to steer (L/R)
        5: Units (N = nautical miles)
        6: Mode indicator
        """
        fields = message.split(",")
        if len(fields) < 6:
            raise ValueError("Invalid XTE message")

        try:
            # Skip first two status fields
            status1, status2 = fields[1:3]
            if status1 != "A" or status2 != "A":
                # Invalid data status
                magnitude = 0.0
            else:
                # Get magnitude and direction
                try:
                    magnitude = float(fields[3])
                    if fields[4] == "L":
                        magnitude = -magnitude
                except ValueError:
                    magnitude = 0.0

            # Convert from nautical miles to meters
            magnitude_meters = magnitude * 1852  # 1 nautical mile = 1852 meters

            # Pack XTE data
            data = struct.pack(
                "<BBBii",
                0xFF,  # SID (not used)
                0xFF,  # XTE mode (not used)
                0,  # Reserved
                int(magnitude_meters * 100),  # XTE in centimeters
                0,  # Reserved
            )

            return NMEA2000Message(
                pgn=PGN.XTE, priority=3, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting XTE: {e}")

    def _clamp_heading(self, heading: float) -> int:
        """Clamp heading to valid range and convert to 1/10000th degree"""
        heading = heading % 360  # Normalize to 0-360
        # Convert to 1/10000th degree and ensure within 16-bit range
        return min(32767, max(-32768, int(heading * 10000)))

    def convert_heading_to_2000(self, message: str) -> NMEA2000Message:
        """
        Convert heading messages (HDT/HDM/HDG) to NMEA 2000 Vessel Heading (PGN 127250)
        """
        fields = message.split(",")
        msg_type = self._get_message_type(message)

        try:
            heading = float(fields[1])
            reference = 0  # 0=True, 1=Magnetic
            deviation = 0.0
            variation = 0.0

            if msg_type == "HDT":
                reference = 0  # True heading
            elif msg_type == "HDM":
                reference = 1  # Magnetic heading
            elif msg_type == "HDG":
                reference = 1  # Magnetic heading
                # Parse deviation
                if len(fields) > 2 and fields[2]:
                    deviation = float(fields[2])
                    if fields[3] == "W":
                        deviation = -deviation
                # Parse variation
                if len(fields) > 4 and fields[4]:
                    variation = float(fields[4])
                    if fields[5].startswith("W"):
                        variation = -variation

            # Clamp values to valid ranges
            heading_value = self._clamp_heading(heading)
            deviation_value = self._clamp_heading(deviation)
            variation_value = self._clamp_heading(variation)

            # Pack heading data
            data = struct.pack(
                "<BBhhh",  # Changed to signed short (h) for all angular values
                0xFF,  # SID (not used)
                reference & 0xFF,  # Reference (0=True, 1=Magnetic)
                heading_value,  # Heading in 1/10000th of a degree
                deviation_value,  # Deviation in 1/10000th of a degree
                variation_value,  # Variation in 1/10000th of a degree
            )

            return NMEA2000Message(
                pgn=PGN.VESSEL_HEADING, priority=2, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting {msg_type}: {e}")

    def convert_rmb_to_2000(self, message: str) -> NMEA2000Message:
        """
        Convert RMB message to NMEA 2000 Navigation Data (PGN 129284)
        """
        fields = message.split(",")
        if len(fields) < 14:
            raise ValueError("Invalid RMB message")

        try:
            # Parse RMB fields
            xte = float(fields[2]) if fields[2] else 0.0
            if fields[3] == "L":
                xte = -xte

            # Parse waypoint coordinates
            wp_lat = self._parse_nmea_lat(fields[6], fields[7])
            wp_lon = self._parse_nmea_lon(fields[8], fields[9])

            distance = float(fields[10]) if fields[10] else 0.0
            bearing = float(fields[11]) if fields[11] else 0.0
            vmg = float(fields[12]) if fields[12] else 0.0

            # Convert units and clamp values
            xte_cm = int(xte * 100 * 185200)  # Convert NM to cm
            distance_cm = int(distance * 100 * 185200)  # Convert NM to cm
            bearing_val = self._clamp_heading(bearing)
            vmg_cms = int(vmg * 51.4444)  # Convert knots to cm/s

            # Pack navigation data
            data = struct.pack(
                "<BBBBiiiihhhh",
                0xFF,  # SID (not used)
                0x01,  # Distance to waypoint reference (1 = Great Circle)
                0x00,  # Perpendicular crossed (0 = Not crossed)
                0x00,  # Arrival circle entered (0 = Not entered)
                xte_cm,  # XTE in centimeters
                int(wp_lat * 1e7),  # Destination latitude
                int(wp_lon * 1e7),  # Destination longitude
                distance_cm,  # Distance to waypoint in centimeters
                bearing_val,  # Bearing reference to destination
                vmg_cms,  # VMG in cm/s
                0,  # Reserved
                0,  # Reserved
            )

            return NMEA2000Message(
                pgn=PGN.NAVIGATION_DATA,
                priority=2,
                source=0,
                destination=255,
                data=data,
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting RMB: {e}")

    def convert_vhw_to_2000(self, message: str) -> NMEA2000Message:
        """
        Convert VHW message to NMEA 2000 Speed (PGN 128259)
        """
        fields = message.split(",")
        if len(fields) < 8:
            raise ValueError("Invalid VHW message")

        try:
            # Get speed through water in knots
            speed = float(fields[5]) if fields[5] else 0.0

            # Convert to centimeters/second (1 knot = 51.4444 cm/s)
            speed_cms = int(speed * 51.4444)

            # Pack speed data
            data = struct.pack(
                "<BBhh",  # Changed format to match NMEA 2000 spec
                0xFF,  # SID (not used)
                0x00,  # Speed reference (0 = Paddle wheel)
                speed_cms,  # Speed through water
                -32767,  # Speed through ground (not available)
            )

            return NMEA2000Message(
                pgn=PGN.SPEED, priority=2, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting VHW: {e}")

    def convert_rsa_to_2000(self, message: str) -> NMEA2000Message:
        """
        Convert RSA message to NMEA 2000 Rudder (PGN 127245)
        """
        fields = message.split(",")
        if len(fields) < 4:
            raise ValueError("Invalid RSA message")

        try:
            # Parse rudder angles
            starboard = float(fields[1]) if fields[1] else 0.0
            port = float(fields[3]) if len(fields) > 3 and fields[3] else starboard

            # Convert to 1/10000th degree and clamp
            starboard_val = self._clamp_heading(starboard)
            port_val = self._clamp_heading(port)

            # Pack rudder data
            data = struct.pack(
                "<BBhh",  # Simplified format to match actual NMEA 2000 spec
                0xFF,  # SID (not used)
                0x00,  # Rudder instance (0 = Main)
                starboard_val,  # Direction order (positive = starboard)
                port_val,  # Position (positive = starboard)
            )

            return NMEA2000Message(
                pgn=PGN.RUDDER, priority=2, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting RSA: {e}")

    def convert_mwd_to_2000(self, message: str) -> NMEA2000Message:
        """
        Convert MWD message to NMEA 2000 Wind Data (PGN 130306)
        """
        fields = message.split(",")
        if len(fields) < 8:
            raise ValueError("Invalid MWD message")

        try:
            # Parse wind direction and speed
            wind_dir = float(fields[1]) if fields[1] else 0.0
            wind_speed = float(fields[5]) if fields[5] else 0.0

            # Convert wind speed to m/s (1 knot = 0.514444 m/s)
            wind_speed_ms = wind_speed * 0.514444

            # Clamp values to valid ranges
            wind_dir_val = self._clamp_heading(wind_dir)
            wind_speed_val = min(32767, max(-32768, int(wind_speed_ms * 100)))

            # Pack wind data
            data = struct.pack(
                "<BBhh",  # Simplified format to match NMEA 2000 spec
                0xFF,  # SID (not used)
                0x00,  # Wind reference (0 = True)
                wind_speed_val,  # Wind speed in 0.01 m/s
                wind_dir_val,  # Wind angle in 1/10000th of a degree
            )

            return NMEA2000Message(
                pgn=PGN.WIND_DATA, priority=2, source=0, destination=255, data=data
            )

        except (ValueError, IndexError) as e:
            raise ValueError(f"Error converting MWD: {e}")

    def _parse_nmea_lat(self, lat: str, ns: str) -> float:
        """Convert NMEA latitude format to decimal degrees"""
        if not lat:
            return 0.0
        try:
            degrees = float(lat[:2])
            minutes = float(lat[2:])
            decimal = degrees + minutes / 60.0
            return -decimal if ns == "S" else decimal
        except (ValueError, IndexError):
            return 0.0

    def _parse_nmea_lon(self, lon: str, ew: str) -> float:
        """Convert NMEA longitude format to decimal degrees"""
        if not lon:
            return 0.0
        try:
            degrees = float(lon[:3])
            minutes = float(lon[3:])
            decimal = degrees + minutes / 60.0
            return -decimal if ew == "W" else decimal
        except (ValueError, IndexError):
            return 0.0
