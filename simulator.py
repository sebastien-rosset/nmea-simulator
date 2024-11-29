#!/usr/bin/env python3

from socket import socket, AF_INET, SOCK_DGRAM
from dataclasses import dataclass
from datetime import datetime, UTC
import logging
import math
import random
import re
import time
from typing import List, Dict, Optional, Tuple, Union

# Set up logging with timestamp, level, and message
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@dataclass
class AISVessel:
    """Class to hold AIS vessel data"""

    mmsi: int
    name: str = ""
    callsign: str = ""
    ship_type: int = 70  # Default: Cargo
    length: int = 100  # meters
    beam: int = 20  # meters
    draft: float = 5.0  # meters
    position: Dict[str, float] = None  # lat, lon
    sog: float = 0.0  # Speed over ground in knots
    cog: float = 0.0  # Course over ground in degrees
    heading: float = 0.0  # True heading in degrees
    nav_status: int = 0  # 0=Under way using engine
    rot: float = 0.0  # Rate of turn in deg/min


class AISEncoder:
    """Encode AIS messages"""
    # AIS 6-bit ASCII encoding table
    __ais_chars = "0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ\\^_`abcdefghijklmnopqrstuvw"

    @staticmethod
    def encode_string(text: str, length: int) -> str:
        """Encode a string to 6-bit ASCII padded to specified length"""
        if not text:
            return "0" * length

        # Convert to uppercase and pad/truncate to length
        text = text.upper()[:length].ljust(length, "@")

        # Convert each character to 6-bit
        result = ""
        for char in text:
            if char in AISEncoder.__ais_chars:
                index = AISEncoder.__ais_chars.index(char)
                result += f"{index:06b}"
        return result

    @staticmethod
    def encode_int(value: int, bits: int) -> str:
        """Encode an integer using specified number of bits"""
        if value < 0:
            # Handle negative numbers using two's complement
            value = (1 << bits) + value
        return f"{value & ((1 << bits) - 1):0{bits}b}"

    @staticmethod
    def encode_float(value: float, bits: int, scale: float) -> str:
        """Encode a floating point value using specified bits and scale"""
        return AISEncoder.encode_int(int(round(value * scale)), bits)

    @staticmethod
    def binary_to_payload(binary: str) -> str:
        """Convert binary string to AIS ASCII payload"""
        # Pad to multiple of 6 bits
        padding = (6 - (len(binary) % 6)) % 6
        binary += "0" * padding

        # Convert each 6 bits to AIS character
        result = ""
        for i in range(0, len(binary), 6):
            chunk = binary[i:i + 6]
            value = int(chunk, 2)
            result += AISEncoder.__ais_chars[value]

        return result

    @staticmethod
    def encode_position_report(vessel: AISVessel) -> str:
        """Encode AIS Position Report (Message Type 1)"""
        binary = ""
        binary += AISEncoder.encode_int(1, 6)  # Message Type
        binary += AISEncoder.encode_int(0, 2)  # Repeat Indicator
        binary += AISEncoder.encode_int(vessel.mmsi, 30)  # MMSI
        binary += AISEncoder.encode_int(vessel.nav_status, 4)  # Navigation Status
        binary += AISEncoder.encode_int(int(vessel.rot), 8)  # Rate of Turn
        binary += AISEncoder.encode_float(vessel.sog, 10, 10)  # Speed Over Ground
        binary += AISEncoder.encode_int(1, 1)  # Position Accuracy
        binary += AISEncoder.encode_float(vessel.position['lon'], 28, 600000)  # Longitude
        binary += AISEncoder.encode_float(vessel.position['lat'], 27, 600000)  # Latitude
        binary += AISEncoder.encode_float(vessel.cog, 12, 10)  # Course Over Ground
        binary += AISEncoder.encode_float(vessel.heading, 9, 1)  # True Heading
        binary += AISEncoder.encode_int(int(datetime.now().second), 6)  # Timestamp
        binary += AISEncoder.encode_int(0, 2)  # Maneuver Indicator
        binary += AISEncoder.encode_int(0, 3)  # Spare
        binary += "1"  # RAIM flag
        binary += AISEncoder.encode_int(0, 19)  # Radio status

        return AISEncoder.binary_to_payload(binary)

    @staticmethod
    def encode_static_data(vessel: AISVessel) -> str:
        """Encode AIS Static and Voyage Related Data (Message Type 5)"""
        binary = ""
        binary += AISEncoder.encode_int(5, 6)  # Message Type
        binary += AISEncoder.encode_int(0, 2)  # Repeat Indicator
        binary += AISEncoder.encode_int(vessel.mmsi, 30)  # MMSI
        binary += AISEncoder.encode_int(0, 2)  # AIS Version
        binary += AISEncoder.encode_int(vessel.mmsi, 30)  # IMO Number
        binary += AISEncoder.encode_string(vessel.callsign, 42)  # Callsign
        binary += AISEncoder.encode_string(vessel.name, 120)  # Vessel Name
        binary += AISEncoder.encode_int(vessel.ship_type, 8)  # Ship Type
        binary += AISEncoder.encode_int(vessel.length, 9)  # Length
        binary += AISEncoder.encode_int(vessel.beam, 6)  # Beam
        binary += AISEncoder.encode_float(vessel.draft, 8, 10)  # Draft
        binary += AISEncoder.encode_int(0, 20)  # Destination
        binary += AISEncoder.encode_int(0, 6)  # ETA month/day
        binary += AISEncoder.encode_int(0, 4)  # ETA hour
        binary += AISEncoder.encode_int(0, 6)  # ETA minute
        binary += "0" * 6  # Padding

        return AISEncoder.binary_to_payload(binary)

class BasicNavSimulator:
    def __init__(self, udp_host="127.0.0.1", udp_port=10110):
        self.sock = socket(AF_INET, SOCK_DGRAM)
        self.udp_host = udp_host
        self.udp_port = udp_port

        # Vessel state
        self.position = {"lat": 0, "lon": 0}
        self.sog = 8  # Speed over ground in knots
        self.cog = 0  # Course Over Ground in degrees true
        self.heading = 0  # Heading in degrees true
        self.variation = -15.0  # Magnetic variation (East negative)

        # Waypoint handling
        self.waypoints = []
        self.current_waypoint_index = 0
        self.waypoint_threshold = 0.1  # nautical miles
        self.reverse_direction = False  # New flag for direction of travel

        self.gps_quality = 1  # GPS fix
        self.satellites_in_use = 8  # Number of satellites
        self.hdop = 1.0  # Horizontal dilution of precision
        self.altitude = 0.0  # Antenna altitude in meters
        self.geoid_separation = 0.0  # Geoidal separation in meters
        self.dgps_age = ""  # Age of DGPS data (empty if not using DGPS)
        self.dgps_station = ""  # DGPS station ID (empty if not using DGPS)

        self.depth = 10.0  # Depth in meters

        self.current_speed = 0.0  # Current speed in knots
        self.current_direction = 0.0  # Current direction in degrees true
        self.water_speed = 0.0  # Speed through water in knots

        # Rudder properties
        self.starboard_rudder = 0.0  # Angle in degrees, negative = port
        self.port_rudder = 0.0  # For dual rudder vessels
        self.max_rudder_angle = 35.0  # Maximum rudder deflection
        self.has_dual_rudder = False  # Set True for vessels with dual rudders

        # Add wind-related properties
        self.true_wind_speed = 0.0  # Wind speed in knots
        self.true_wind_direction = 0.0  # Direction wind is coming FROM in degrees true
        self.apparent_wind_speed = 0.0  # Apparent wind speed in knots
        self.apparent_wind_angle = (
            0.0  # Apparent wind angle relative to bow (-180 to +180)
        )

        # Add AIS vessels list
        self.ais_vessels: List[AISVessel] = []
        self.last_ais_update = 0
        self.ais_update_interval = 10  # seconds between AIS updates

    def calculate_nmea_checksum(self, sentence: str) -> str:
        """
        Calculate NMEA checksum by XORing all characters between $ or ! and *

        Args:
            sentence: NMEA sentence string

        Returns:
            Two-character hex string of checksum
        """
        # Start from character after $ or ! until * (or end of string)
        start = 1  # Skip first character ($ or !)
        end = sentence.find("*")
        if end == -1:  # If no * found, process whole string
            end = len(sentence)

        # XOR all characters between start and end
        checksum = 0
        for char in sentence[start:end]:
            checksum ^= ord(char)

        # Return two-character hex string
        return f"{checksum:02X}"

    def send_nmea(self, sentence):
        if not sentence.startswith("$"):
            sentence = "$" + sentence

        # Calculate checksum before adding terminators
        checksum = self.calculate_nmea_checksum(sentence)
        # Format complete sentence with checksum and terminators
        full_sentence = f"{sentence}*{checksum}\r\n"
        logging.info(f"Sending NMEA: {full_sentence.strip()}")
        if not sentence.endswith("\r\n"):
            sentence = sentence + "\r\n"
        self.sock.sendto(full_sentence.encode(), (self.udp_host, self.udp_port))

    def format_lat(self, lat):
        """Convert decimal degrees to NMEA ddmm.mmm,N/S format"""
        hemisphere = "N" if lat >= 0 else "S"
        lat = abs(lat)
        degrees = int(lat)
        minutes = (lat - degrees) * 60
        return f"{degrees:02d}{minutes:06.3f},{hemisphere}"

    def format_lon(self, lon):
        """Convert decimal degrees to NMEA dddmm.mmm,E/W format"""
        hemisphere = "E" if lon >= 0 else "W"
        lon = abs(lon)
        degrees = int(lon)
        minutes = (lon - degrees) * 60
        return f"{degrees:03d}{minutes:06.3f},{hemisphere}"

    def parse_coordinate(self, coord: Union[str, float, int]) -> float:
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
        self, lat1: float, lon1: float, lat2: float, lon2: float
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

    def get_distance_to_next_waypoint(self):
        """Calculate distance between current position and next way point in nautical miles"""
        if self.current_waypoint_index >= len(self.waypoints):
            return 0

        next_waypoint = self.waypoints[self.current_waypoint_index]
        current_pos = self.position
        return self.calculate_distance(
            current_pos["lat"],
            current_pos["lon"],
            next_waypoint["lat"],
            next_waypoint["lon"],
        )

    def calculate_bearing(
        self, lat1: float, lon1: float, lat2: float, lon2: float
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

    def update_course_to_waypoint(self):
        """Update course to head towards the current waypoint"""
        if not self.waypoints:
            return False

        next_waypoint = self.waypoints[self.current_waypoint_index]
        current_pos = self.position

        # Calculate distance and bearing to next waypoint
        distance = self.calculate_distance(
            current_pos["lat"],
            current_pos["lon"],
            next_waypoint["lat"],
            next_waypoint["lon"],
        )

        # If we're close enough to waypoint, move to next one
        if distance < self.waypoint_threshold:
            logging.info(f"Reached waypoint {self.current_waypoint_index}")

            if self.reverse_direction:
                self.current_waypoint_index -= 1
                if self.current_waypoint_index < 0:
                    logging.info("Reached first waypoint, reversing direction")
                    self.current_waypoint_index = 1
                    self.reverse_direction = False
            else:
                self.current_waypoint_index += 1
                if self.current_waypoint_index >= len(self.waypoints):
                    logging.info("Reached last waypoint, reversing direction")
                    self.current_waypoint_index = len(self.waypoints) - 2
                    self.reverse_direction = True

            return self.update_course_to_waypoint()

        # Update course to point to waypoint
        self.cog = self.calculate_bearing(
            current_pos["lat"],
            current_pos["lon"],
            next_waypoint["lat"],
            next_waypoint["lon"],
        )

        return True

    def update_water_speed(self):
        """
        Calculate speed through water based on SOG and current.
        Uses vector addition of vessel movement and water current.
        """
        # Convert angles to radians
        vessel_dir_rad = math.radians(self.cog)
        current_dir_rad = math.radians(self.current_direction)

        # Convert speeds and directions to vectors
        # Vessel vector (SOG)
        vx = self.sog * math.sin(vessel_dir_rad)
        vy = self.sog * math.cos(vessel_dir_rad)

        # Current vector
        cx = self.current_speed * math.sin(current_dir_rad)
        cy = self.current_speed * math.cos(current_dir_rad)

        # Subtract current vector to get water speed vector
        wx = vx - cx
        wy = vy - cy

        # Calculate water speed
        self.water_speed = math.sqrt(wx * wx + wy * wy)

    def update_rudder_angle(self, desired_heading: float, delta_time: float):
        """
        Update rudder angle based on desired vs current heading.
        Simple P controller for rudder adjustment.

        Args:
            desired_heading: Target heading in degrees
            delta_time: Time step in seconds
        """

        # Calculate heading error (-180 to +180 degrees)
        error = (desired_heading - self.heading + 180) % 360 - 180

        # Simple proportional control
        # Adjust these gains to change how aggressively the rudder responds
        P_GAIN = 2.0

        # Calculate desired rudder angle
        desired_rudder = P_GAIN * error

        # Limit rudder angle to maximum deflection
        desired_rudder = max(
            -self.max_rudder_angle, min(self.max_rudder_angle, desired_rudder)
        )

        # Apply rudder movement rate limit (typical 2.5-3 degrees per second)
        MAX_RATE = 3.0  # degrees per second
        max_change = MAX_RATE * delta_time
        current = self.starboard_rudder

        if abs(desired_rudder - current) <= max_change:
            self.starboard_rudder = desired_rudder
        else:
            # Move towards desired angle at maximum rate
            self.starboard_rudder += (
                max_change if desired_rudder > current else -max_change
            )

        # For dual rudder vessels, mirror the starboard rudder
        if self.has_dual_rudder:
            self.port_rudder = self.starboard_rudder

    def send_rsa(self):
        """
        Create an RSA (Rudder Sensor Angle) sentence.
        Format: $--RSA,x.x,A,x.x,A*hh

        Angle is positive for starboard helm, negative for port helm.
        """
        if self.has_dual_rudder:
            # Dual rudder format
            rsa = (
                f"HCRSA,"
                f"{self.starboard_rudder:.1f},A,"  # Starboard rudder + status
                f"{self.port_rudder:.1f},A"  # Port rudder + status
            )
        else:
            # Single rudder format
            rsa = (
                f"HCRSA,"
                f"{self.starboard_rudder:.1f},A,"  # Single rudder + status
                f","  # Empty port rudder fields
            )

        self.send_nmea(rsa)

    def send_vhw(self):
        """
        Create a VHW (Water Speed and Heading) sentence.
        Format: $--VHW,x.x,T,x.x,M,x.x,N,x.x,K*hh
        """
        # Update water speed calculations
        self.update_water_speed()

        # Calculate magnetic heading
        magnetic_heading = (self.heading + self.variation) % 360

        # Convert water speed to km/h
        speed_kmh = self.water_speed * 1.852  # 1 knot = 1.852 km/h

        # Build the VHW sentence
        vhw = (
            f"VWVHW,"
            f"{self.heading:.1f},T,"  # True heading
            f"{magnetic_heading:.1f},M,"  # Magnetic heading
            f"{self.water_speed:.1f},N,"  # Speed in knots
            f"{speed_kmh:.1f},K"  # Speed in km/h
        )
        self.send_nmea(vhw)

    def set_current(self, speed: float, direction: float):
        """
        Set water current parameters.

        Args:
            speed: Current speed in knots
            direction: Current direction in degrees true (direction current is flowing TOWARDS)
        """
        self.current_speed = speed
        # Store direction as normalized 0-360
        self.current_direction = direction % 360

    def send_gga(self):
        """
        Create a GGA (Global Positioning System Fix Data) sentence.

        Returns:
            str: Formatted NMEA GGA sentence
        """
        now = datetime.now(UTC)
        timestamp = now.strftime("%H%M%S.00")

        # Build the GGA sentence
        gga = (
            f"GPGGA,"
            f"{timestamp},"
            f"{self.format_lat(self.position['lat'])},"
            f"{self.format_lon(self.position['lon'])},"
            f"{self.gps_quality},"
            f"{self.satellites_in_use:02d},"  # 00-12 satellites, leading zero
            f"{self.hdop:.1f},"
            f"{self.altitude:.1f},M,"  # Altitude and units
            f"{self.geoid_separation:.1f},M,"  # Geoid separation and units
            f"{self.dgps_age},"  # DGPS age (empty if not used)
            f"{self.dgps_station}"  # DGPS station ID (empty if not used)
        )
        self.send_nmea(gga)

    def calculate_cross_track_error(self) -> Tuple[float, str]:
        """
        Calculate cross track error and direction between current position and route leg.

        Returns:
            Tuple[float, str]: (XTE magnitude in nautical miles, direction to steer 'L' or 'R')
        """
        if self.current_waypoint_index == 0 or self.current_waypoint_index >= len(
            self.waypoints
        ):
            return 0.0, "L"  # No XTE when not navigating between waypoints

        # Get current leg waypoints
        start = self.waypoints[self.current_waypoint_index - 1]
        end = self.waypoints[self.current_waypoint_index]

        # Convert to radians for calculations
        lat1, lon1 = map(math.radians, [start["lat"], start["lon"]])
        lat2, lon2 = map(math.radians, [end["lat"], end["lon"]])
        lat3, lon3 = map(math.radians, [self.position["lat"], self.position["lon"]])

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

    def send_xte(self):
        """
        Create an XTE (Cross-Track Error) sentence.

        Returns:
            str: Formatted NMEA XTE sentence
        """
        # Calculate XTE and steering direction
        xte_magnitude, steer_direction = self.calculate_cross_track_error()

        # Build the XTE sentence (using NMEA 2.3 format with mode indicator)
        xte = (
            f"GPXTE,"
            f"A,A,"  # Both status fields valid
            f"{xte_magnitude:.1f},"  # XTE magnitude
            f"{steer_direction},"  # Direction to steer (L/R)
            f"N,"  # Units (Nautical Miles)
            f"A"  # Mode indicator (A=Autonomous)
        )
        self.send_nmea(xte)

    def send_dbt(self):
        """
        Create a DBT (Depth Below Transducer) sentence.

        Converts the depth in meters to feet and fathoms and formats according to NMEA spec.
        Returns:
            str: Formatted NMEA DBT sentence
        """
        # Conversion factors
        METERS_TO_FEET = 3.28084
        METERS_TO_FATHOMS = 0.546807

        # Convert depth from meters to other units
        depth_feet = self.depth * METERS_TO_FEET
        depth_fathoms = self.depth * METERS_TO_FATHOMS

        # Build the DBT sentence with all three measurements
        dbt = (
            f"SDDBT,"
            f"{depth_feet:.1f},f,"
            f"{self.depth:.1f},M,"
            f"{depth_fathoms:.1f},F"
        )
        self.send_nmea(dbt)

    def calculate_vmg(self, bearing_to_waypoint: float) -> float:
        """Calculate Velocity Made Good towards waypoint"""
        # VMG = SOG * cos(COG - BRG)
        angle_diff = math.radians(abs(self.cog - bearing_to_waypoint))
        return self.sog * math.cos(angle_diff)

    def send_rmb(self):
        """
        Create an RMB (Recommended Minimum Navigation Information) sentence.
        To be sent when a destination waypoint is active.
        """
        if self.current_waypoint_index >= len(self.waypoints):
            return  # No active waypoint

        # Get current waypoint data
        current_waypoint = self.waypoints[self.current_waypoint_index]

        # Calculate XTE and steering direction
        xte_magnitude, steer_direction = self.calculate_cross_track_error()

        # Calculate range and bearing to destination
        distance = self.calculate_distance(
            self.position["lat"],
            self.position["lon"],
            current_waypoint["lat"],
            current_waypoint["lon"],
        )

        bearing = self.calculate_bearing(
            self.position["lat"],
            self.position["lon"],
            current_waypoint["lat"],
            current_waypoint["lon"],
        )

        # Calculate VMG (Velocity Made Good) towards waypoint
        vmg = self.calculate_vmg(bearing)

        # Determine if we've entered arrival circle
        arrival_status = "A" if distance < self.waypoint_threshold else "V"

        # Format waypoint coordinates
        wp_lat = self.format_lat(current_waypoint["lat"]).split(",")
        wp_lon = self.format_lon(current_waypoint["lon"]).split(",")

        # Previous waypoint ID (if available)
        from_waypoint = (
            f"WP{self.current_waypoint_index-1:03d}"
            if self.current_waypoint_index > 0
            else ""
        )

        # Current waypoint ID
        to_waypoint = f"WP{self.current_waypoint_index:03d}"

        # Build the RMB sentence
        rmb = (
            f"GPRMB,"
            f"A,"  # Status (Active)
            f"{xte_magnitude:.1f},"  # Cross Track Error
            f"{steer_direction},"  # Direction to steer (L/R)
            f"{from_waypoint},"  # FROM Waypoint ID
            f"{to_waypoint},"  # TO Waypoint ID
            f"{wp_lat[0]},"  # Destination Waypoint Latitude
            f"{wp_lat[1]},"  # N/S
            f"{wp_lon[0]},"  # Destination Waypoint Longitude
            f"{wp_lon[1]},"  # E/W
            f"{distance:.1f},"  # Range to destination
            f"{bearing:.1f},"  # Bearing to destination
            f"{vmg:.1f},"  # Destination closing velocity (VMG)
            f"{arrival_status},"  # Arrival Status
            f"A"  # Navigation Status & Mode Indicator
        )
        self.send_nmea(rmb)

    def send_ais_message(self, body: str, message_type: int, channel: str = "A"):
        """Send an AIS message in NMEA format"""
        # Split message into 168-character fragments
        max_len = 168
        fragments = [body[i:i + max_len] for i in range(0, len(body), max_len)]
        
        for i, fragment in enumerate(fragments):
            # Calculate fragment count and number
            frag_count = len(fragments)
            frag_num = i + 1
            
            # Build AIVDM sentence
            sentence = f"!AIVDM,{frag_count},{frag_num},,{channel},{fragment},0"
            
            # Add checksum and send
            self.send_nmea(sentence)

    def update_ais_vessels(self, delta_time: float):
        """Update AIS vessel positions and send messages"""
        current_time = time.time()
        
        # Only update AIS data at specified interval
        if current_time - self.last_ais_update < self.ais_update_interval:
            return
            
        for vessel in self.ais_vessels:
            # Update vessel position based on course and speed
            if vessel.position:
                # Convert speed to meters per second
                speed_ms = vessel.sog * 0.514444
                
                # Calculate movement
                heading_rad = math.radians(vessel.cog)
                dx = speed_ms * math.sin(heading_rad) * delta_time
                dy = speed_ms * math.cos(heading_rad) * delta_time
                
                # Convert to coordinate changes
                R = 6371000  # Earth radius in meters
                lat_rad = math.radians(vessel.position['lat'])
                
                dlat = math.degrees(dy / R)
                dlon = math.degrees(dx / (R * math.cos(lat_rad)))
                
                # Update position
                vessel.position['lat'] += dlat
                vessel.position['lon'] += dlon
                
                # Send position report
                pos_report = AISEncoder.encode_position_report(vessel)
                self.send_ais_message(pos_report, 1)
                
                # Occasionally send static data
                if random.random() < 0.1:  # 10% chance each update
                    static_data = AISEncoder.encode_static_data(vessel)
                    self.send_ais_message(static_data, 5)
        
        self.last_ais_update = current_time

    def calculate_apparent_wind(self):
        """
        Calculate apparent wind based on true wind and vessel movement.
        Uses vector mathematics to combine true wind and vessel motion.
        """
        # Convert angles to radians
        true_wind_dir_rad = math.radians(self.true_wind_direction)
        vessel_heading_rad = math.radians(self.heading)

        # Convert true wind to vector components
        true_wind_x = self.true_wind_speed * math.sin(true_wind_dir_rad)
        true_wind_y = self.true_wind_speed * math.cos(true_wind_dir_rad)

        # Convert vessel motion to vector components
        vessel_x = self.sog * math.sin(vessel_heading_rad)
        vessel_y = self.sog * math.cos(vessel_heading_rad)

        # Calculate apparent wind components by subtracting vessel motion
        apparent_x = true_wind_x - vessel_x
        apparent_y = true_wind_y - vessel_y

        # Calculate apparent wind speed
        self.apparent_wind_speed = math.sqrt(apparent_x**2 + apparent_y**2)

        # Calculate apparent wind angle relative to vessel heading
        apparent_angle_rad = math.atan2(apparent_x, apparent_y) - vessel_heading_rad

        # Convert to degrees and normalize to -180 to +180
        self.apparent_wind_angle = math.degrees(apparent_angle_rad)
        if self.apparent_wind_angle > 180:
            self.apparent_wind_angle -= 360
        elif self.apparent_wind_angle < -180:
            self.apparent_wind_angle += 360

    def send_mwv(self, is_true: bool):
        """
        Send MWV (Wind Speed and Angle) sentence.
        Format: $--MWV,x.x,a,x.x,a,A*hh
        Fields: wind angle, reference (R/T), wind speed, wind speed units, status
        """
        if is_true:
            # For true wind, calculate angle relative to bow
            relative_angle = (self.true_wind_direction - self.heading) % 360
            if relative_angle > 180:
                relative_angle -= 360
            wind_speed = self.true_wind_speed
            reference = "T"
        else:
            # For apparent wind, use calculated apparent values
            relative_angle = self.apparent_wind_angle
            wind_speed = self.apparent_wind_speed
            reference = "R"

        # Ensure angle is positive (0-360) for NMEA format
        if relative_angle < 0:
            relative_angle += 360

        mwv = (
            f"WIMWV,"
            f"{relative_angle:.1f},"  # Wind angle
            f"{reference},"  # Reference: R (Relative/Apparent) or T (True)
            f"{wind_speed:.1f},"  # Wind speed
            f"N,"  # Units: N for knots
            f"A"  # Status: A for valid data
        )
        self.send_nmea(mwv)

    def send_mwd(self):
        """
        Send MWD (Wind Direction and Speed) sentence.
        Format: $--MWD,x.x,T,x.x,M,x.x,N,x.x,M*hh
        Fields: wind direction true, T, wind direction magnetic, M,
                wind speed knots, N, wind speed m/s, M
        """
        # Calculate magnetic wind direction
        magnetic_wind_dir = (self.true_wind_direction + self.variation) % 360

        # Convert wind speed to m/s
        wind_speed_ms = self.true_wind_speed * 0.514444  # Convert knots to m/s

        mwd = (
            f"WIMWD,"
            f"{self.true_wind_direction:.1f},T,"  # True wind direction
            f"{magnetic_wind_dir:.1f},M,"  # Magnetic wind direction
            f"{self.true_wind_speed:.1f},N,"  # Wind speed in knots
            f"{wind_speed_ms:.1f},M"  # Wind speed in m/s
        )
        self.send_nmea(mwd)

    def send_essential_data(self):
        """Send RMC, HDT, HDG sentences"""
        now = datetime.now(UTC)
        timestamp = now.strftime("%H%M%S.00")
        date = now.strftime("%d%m%y")

        # RMC - Recommended Minimum Navigation Information.
        # Talker ID is GN for GPS, GA for Galileo, GL for GLONASS.
        rmc = (
            f"GPRMC,{timestamp},A,"
            f"{self.format_lat(self.position['lat'])},"
            f"{self.format_lon(self.position['lon'])},"
            f"{self.sog:.1f},{self.cog:.1f},{date},"
            f"{abs(self.variation):.1f},{'E' if self.variation >= 0 else 'W'},,A"
        )
        self.send_nmea(rmc)

        # HDT - Heading True, usually from a gyrocompass. Talker ID is HE.
        hdt = f"HEHDT,{self.heading:.1f},T"
        self.send_nmea(hdt)

        # HDM - Heading Magnetic, usually from a magnetic compass. Talker ID is HE.
        magnetic_heading = (self.heading + self.variation) % 360
        hdm = f"HEHDM,{magnetic_heading:.1f},M"
        self.send_nmea(hdm)

        # HDG - Heading with variation/deviation, usually from a fluxgate compass. Talker ID is HE.
        hdg = f"HEHDG,{self.heading:.1f},0.0,E,{abs(self.variation):.1f},W"
        self.send_nmea(hdg)

        # # VTG - Track Made Good and Ground Speed
        # vtg = f"GPVTG,{self.cog:.1f},T,{self.cog:.1f},M,{self.sog:.1f},N,{self.sog*1.852:.1f},K,A"
        # self.send_nmea(vtg)

    def update_position(self, delta_time):
        """
        Update position based on heading and speed, accounting for:
        - Rudder angle effect on heading
        - Water current
        - Reduced effectiveness when heading differs from course
        """
        # Skip update if delta_time is too small
        if delta_time < 0.001:  # Less than 1ms
            return

        # First update the rudder based on desired course
        self.update_rudder_angle(self.cog, delta_time)

        # Rudder effect on turn rate
        RUDDER_TURN_RATE = 1.0  # degrees per second at full rudder
        turn_rate = (self.starboard_rudder / self.max_rudder_angle) * RUDDER_TURN_RATE

        # Update heading based on rudder
        self.heading = (self.heading + turn_rate * delta_time) % 360

        # Convert commanded speed to meters per second
        commanded_speed_ms = self.sog * 0.514444  # Convert knots to m/s
        current_speed_ms = self.current_speed * 0.514444

        # Convert angles to radians
        heading_rad = math.radians(self.heading)
        current_dir_rad = math.radians(self.current_direction)

        # Calculate ship movement vector based on actual heading
        # Always use full commanded speed - the ship maintains its engine power
        ship_dx = commanded_speed_ms * math.sin(heading_rad)
        ship_dy = commanded_speed_ms * math.cos(heading_rad)

        # Calculate current vector
        current_dx = current_speed_ms * math.sin(current_dir_rad)
        current_dy = current_speed_ms * math.cos(current_dir_rad)

        # Combined movement vector (ship + current)
        total_dx = (ship_dx - current_dx) * delta_time  # Subtract current effect
        total_dy = (ship_dy - current_dy) * delta_time

        # Convert to angular distances
        R = 6371000  # Earth radius in meters
        lat_rad = math.radians(self.position["lat"])

        # Update position
        dlat = math.degrees(total_dy / R)
        # Adjust longitude change based on latitude
        dlon = math.degrees(total_dx / (R * math.cos(lat_rad)))

        # Update position
        self.position["lat"] += dlat
        self.position["lon"] += dlon

        # Update COG based on actual movement vector
        # Calculate actual course from movement vector
        total_dx_per_second = total_dx / delta_time
        total_dy_per_second = total_dy / delta_time

        self.cog = (
            math.degrees(math.atan2(total_dx_per_second, total_dy_per_second)) % 360
        )

    def simulate(
        self,
        waypoints: List[Dict[str, Union[str, float]]],
        duration_seconds: Optional[float] = None,
        update_rate: float = 1,
        wind_direction: float = 0.0,  # Direction wind is coming FROM in degrees true
        wind_speed: float = 0.0,  # Wind speed in knots
        ais_vessels: Optional[List[AISVessel]] = None,
    ):
        """Run the simulation with waypoints"""
        if not waypoints:
            raise ValueError("Must provide at least one waypoint")

        # Initialize AIS vessels if provided
        self.ais_vessels = ais_vessels or []

        # Initialize wind parameters
        self.true_wind_speed = wind_speed
        self.true_wind_direction = wind_direction

        parsed_waypoints = []
        for wp in waypoints:
            parsed_wp = {
                "lat": self.parse_coordinate(wp["lat"]),
                "lon": self.parse_coordinate(wp["lon"]),
            }
            parsed_waypoints.append(parsed_wp)

        self.waypoints = parsed_waypoints
        self.current_waypoint_index = 1  # Start with second waypoint as target
        self.position = {
            "lat": parsed_waypoints[0]["lat"],
            "lon": parsed_waypoints[0]["lon"],
        }
        self.reverse_direction = False

        start_time = time.time()
        last_update = start_time

        try:
            while True:
                current_time = time.time()

                # Check duration if specified
                if (
                    duration_seconds is not None
                    and (current_time - start_time) >= duration_seconds
                ):
                    logging.info("Simulation duration reached")
                    break

                delta_time = current_time - last_update

                # Update AIS vessels
                self.update_ais_vessels(delta_time)

                # Update course to next waypoint
                if not self.update_course_to_waypoint():
                    logging.info("Navigation error - stopping simulation")
                    break

                logging.info(
                    f"Current position: {self.position['lat']:.6f}, {self.position['lon']:.6f}. "
                    f"Heading: {self.heading:.2f}. "
                    f"Distance to waypoint: {self.get_distance_to_next_waypoint():.3f} nm. "
                    f"SOG: {self.sog:.2f}. "
                    f"Direction: {'Reverse' if self.reverse_direction else 'Forward'}"
                )

                # Update simulation state
                self.update_position(delta_time)

                # Calculate apparent wind based on true wind and vessel motion
                self.calculate_apparent_wind()

                # Send all instrument data
                self.send_essential_data()
                self.send_gga()  # GPS fix data
                self.send_dbt()  # Depth below transducer
                self.send_xte()  # Cross-track error
                self.send_rmb()  # Recommended Minimum Navigation Information
                self.send_vhw()  # Water speed and heading
                self.send_rsa()  # Rudder angle

                # Send wind data
                self.send_mwv(True)  # True wind
                self.send_mwv(False)  # Apparent wind
                self.send_mwd()  # Wind direction and speed

                last_update = current_time
                time.sleep(update_rate)

        except KeyboardInterrupt:
            logging.info("Simulation stopped by user")

    def __del__(self):
        self.sock.close()


if __name__ == "__main__":
    simulator = BasicNavSimulator()

    # Example waypoints for a route in San Francisco Bay
    waypoints = [
        {"lat": "37° 40.3574' N", "lon": "122° 22.1457' W"},
        {"lat": "37° 43.4444' N", "lon": "122° 20.7058' W"},
        {"lat": "37° 48.0941' N", "lon": "122° 22.7372' W"},
        {"lat": "37° 49.1258' N", "lon": "122° 25.2814' W"},
    ]

    # Create some example AIS vessels
    ais_vessels = [
        AISVessel(
            mmsi=366123456,
            name="GOLDEN GATE",
            callsign="WD123",
            ship_type=70,
            length=200,
            beam=30,
            draft=12.0,
            position={"lat": 37.4049, "lon": -122.2294},
            sog=12.0,
            cog=270.0,
            heading=270.0,
            nav_status=0,
            rot=0.0
        ),
        AISVessel(
            mmsi=366789012,
            name="BAY TRADER",
            callsign="WD456",
            ship_type=80,
            length=150,
            beam=25,
            draft=8.0,
            position={"lat": 37.4085, "lon": -122.208},
            sog=8.0,
            cog=90.0,
            heading=90.0,
            nav_status=0,
            rot=0.0
        )
    ]

    logging.info("Starting simulation...")
    simulator.simulate(
        waypoints=waypoints,
        duration_seconds=None,
        update_rate=1,  # Update every second
        wind_direction=270,  # Wind coming from the west
        wind_speed=15.0,  # 15 knots of wind
        ais_vessels=ais_vessels,
    )
