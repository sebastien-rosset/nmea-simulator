#!/usr/bin/env python3

import bitstring
from socket import socket, AF_INET, SOCK_DGRAM
from dataclasses import dataclass, field
from datetime import datetime, UTC
import logging
import math
import random
import re
import time
from typing import List, Dict, Optional, Tuple, Union

# Set up logging with timestamp, level, and message
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

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


class AISVessel:
    """AIS Vessel class"""

    # AIS Navigation Status codes
    NAV_STATUS = {
        'UNDERWAY_ENGINE': 0,    # Under way using engine
        'AT_ANCHOR': 1,          # At anchor
        'NOT_UNDER_COMMAND': 2,  # Not under command
        'RESTRICTED_MANEUVER': 3,# Restricted maneuverability
        'CONSTRAINED_DRAFT': 4,  # Constrained by draught
        'MOORED': 5,            # Moored
        'AGROUND': 6,           # Aground
        'FISHING': 7,           # Engaged in fishing
        'UNDERWAY_SAILING': 8,  # Under way sailing
    }
    # Ship Types (common ones)
    SHIP_TYPES = {
        'CARGO': 70,      # Cargo ship
        'TANKER': 80,     # Tanker
        'FISHING': 30,    # Fishing vessel
        'SAILING': 36,    # Sailing vessel
        'PILOT': 50,      # Pilot vessel
        'TUG': 52,        # Tug
        'PASSENGER': 60,  # Passenger ship
        'FERRY': 61,      # Ferry
        'DREDGER': 33,    # Dredger
    }
    def __init__(self,
                 mmsi: int,
                 vessel_name: str,
                 position: dict,
                 ship_type: int = None,
                 call_sign: str = None,
                 length: float = None,
                 beam: float = None,
                 draft: float = None,
                 course: float = 0.0,
                 speed: float = 0.0,
                 navigation_status: int = 0,
                 rot: float = 0.0):
        """
        Initialize an AIS vessel with basic parameters
        
        Args:
            mmsi (int): Maritime Mobile Service Identity (9 digits)
            vessel_name (str): Name of the vessel (max 20 chars)
            position (dict): Position with 'lat' and 'lon' keys
            ship_type (int, optional): Type of ship according to AIS specifications
            call_sign (str, optional): Radio call sign (max 7 chars)
            length (float, optional): Length of vessel in meters
            beam (float, optional): Beam/width of vessel in meters
            draft (float, optional): Draft in meters (max 25.5)
            course (float, optional): Course over ground in degrees
            speed (float, optional): Speed over ground in knots
            navigation_status (int, optional): AIS navigation status code
            rot (float, optional): Rate of turn in degrees per minute
        """
        # Required parameters
        if not isinstance(mmsi, int) or len(str(mmsi)) != 9:
            raise ValueError("MMSI must be a 9-digit integer")
        self.mmsi = mmsi
        self.vessel_name = vessel_name[:20]
        
        # Optional parameters with defaults based on ship type
        self.ship_type = ship_type or self.SHIP_TYPES['CARGO']  # Default to cargo ship
        
        # Set reasonable defaults based on ship type
        if self.ship_type == self.SHIP_TYPES['SAILING']:
            self.length = length or 15.0  # Default 15m sailing vessel
            self.beam = beam or 4.0       # Default 4m beam
            self.draft = min(draft or 2.1, 25.5)  # Default 2.1m draft
        elif self.ship_type == self.SHIP_TYPES['FISHING']:
            self.length = length or 25.0  # Default 25m fishing vessel
            self.beam = beam or 8.0       # Default 8m beam
            self.draft = min(draft or 3.5, 25.5)  # Default 3.5m draft
        else:  # Cargo or other large vessels
            self.length = length or 200.0  # Default 200m vessel
            self.beam = beam or 30.0       # Default 30m beam
            self.draft = min(draft or 12.0, 25.5)  # Default 12m draft
            
        self.call_sign = (call_sign or f"V{self.mmsi % 1000000:06d}")[:7]
        self.course = course
        self.speed = speed
        self.rot = rot
        self.navigation_status = navigation_status
        
        # Parse position
        self.position = {}
        if position:
            for key in ['lat', 'lon']:
                if key in position:
                    self.position[key] = parse_coordinate(position[key])

    def encode_rate_of_turn(self):
        """
        Encode rate of turn according to AIS specifications
        ROT = 4.733 * SQRT(rate of turn) degrees per min
        Returns encoded ROT value (-128 to +127)
        """
        if self.rot == 0:
            return 0
        elif self.rot is None:
            return -128  # Not available
        
        # Convert ROT to AIS ROT indicator
        ais_rot = 4.733 * math.sqrt(abs(self.rot))
        ais_rot = round(ais_rot)
        
        # Cap at 126 (708° per minute), negative values indicate port turn
        ais_rot = min(126, ais_rot)
        if self.rot < 0:
            ais_rot = -ais_rot
            
        return ais_rot

    def encode_position_report(self):
        """
        Encode a Position Report (Message Type 1) in AIVDM format
        Returns the payload part of the AIVDM sentence
        """
        # Create a BitArray to hold the message
        bits = bitstring.BitArray()
        
        # Message Type (6 bits) - Position Report is type 1
        bits.append(bitstring.pack('uint:6', 1))
        
        # Repeat Indicator (2 bits)
        bits.append(bitstring.pack('uint:2', 0))
        
        # MMSI (30 bits)
        bits.append(bitstring.pack('uint:30', self.mmsi))
        
        # Navigation Status (4 bits)
        bits.append(bitstring.pack('uint:4', self.navigation_status))
        
        # Rate of Turn (8 bits)
        bits.append(bitstring.pack('int:8', self.encode_rate_of_turn()))
        
        # Speed Over Ground (10 bits) - in 0.1 knot steps
        speed_int = int(self.speed * 10)
        bits.append(bitstring.pack('uint:10', min(speed_int, 1023)))
        
        # Position Accuracy (1 bit) - 0 = low, 1 = high
        bits.append(bitstring.pack('uint:1', 0))
        
        # Longitude (28 bits) - in 1/10000 minute
        lon = int(self.position['lon'] * 600000)
        bits.append(bitstring.pack('int:28', lon))
        
        # Latitude (27 bits) - in 1/10000 minute
        lat = int(self.position['lat'] * 600000)
        bits.append(bitstring.pack('int:27', lat))
        
        # Course Over Ground (12 bits) - in 0.1 degree steps
        cog = int(self.course * 10)
        bits.append(bitstring.pack('uint:12', cog))
        
        # True Heading (9 bits) - use COG if not available
        bits.append(bitstring.pack('uint:9', int(self.course)))
        
        # Time Stamp (6 bits) - seconds of UTC timestamp
        timestamp = datetime.now(UTC).second
        bits.append(bitstring.pack('uint:6', timestamp))
        
        # Reserved (4 bits)
        bits.append(bitstring.pack('uint:4', 0))
        
        # Return the binary data encoded in 6-bit ASCII format
        return self._encode_payload(bits)
    
    def encode_static_data(self):
        """
        Encode Static and Voyage Related Data (Message Type 5)
        Uses 6-bit ASCII encoding as per ITU-R M.1371
        """
        bits = bitstring.BitArray()
        
        # Message Type (6 bits) - Type 5
        bits.append(bitstring.pack('uint:6', 5))
        
        # Repeat Indicator (2 bits)
        bits.append(bitstring.pack('uint:2', 0))
        
        # MMSI (30 bits)
        bits.append(bitstring.pack('uint:30', self.mmsi))
        
        # AIS Version (2 bits)
        bits.append(bitstring.pack('uint:2', 0))
        
        # IMO Number (30 bits) - Using 0 for this example
        bits.append(bitstring.pack('uint:30', 0))
        
        # Call Sign (42 bits) - 7 six-bit characters
        call_sign_padded = self.call_sign.ljust(7)
        for char in call_sign_padded:
            # Convert to 6-bit ASCII as per ITU-R M.1371
            if ord(char) >= 64:  # '@' and above
                sixbit = ord(char) - 64
            elif ord(char) >= 32:  # Space and above
                sixbit = ord(char)
            else:  # Below space
                sixbit = 32  # Default to space
            bits.append(bitstring.pack('uint:6', sixbit))
        
        # Vessel Name (120 bits) - 20 six-bit characters
        name_padded = self.vessel_name.ljust(20)
        for char in name_padded:
            # Convert to 6-bit ASCII
            if ord(char) >= 64:  # '@' and above
                sixbit = ord(char) - 64
            elif ord(char) >= 32:  # Space and above
                sixbit = ord(char)
            else:  # Below space
                sixbit = 32  # Default to space
            bits.append(bitstring.pack('uint:6', sixbit))
        
        # Ship Type (8 bits)
        bits.append(bitstring.pack('uint:8', self.ship_type))
        
        # Dimension to Bow (9 bits)
        bits.append(bitstring.pack('uint:9', int(self.length/2)))
        
        # Dimension to Stern (9 bits)
        bits.append(bitstring.pack('uint:9', int(self.length/2)))
        
        # Dimension to Port (6 bits)
        bits.append(bitstring.pack('uint:6', int(self.beam/2)))
        
        # Dimension to Starboard (6 bits)
        bits.append(bitstring.pack('uint:6', int(self.beam/2)))
        
        # Draft (8 bits) - in 0.1 meter steps
        draft_dm = int(self.draft * 10)
        bits.append(bitstring.pack('uint:8', draft_dm))
        
        # Destination (120 bits) - 20 six-bit characters
        destination = "".ljust(20)
        for char in destination:
            bits.append(bitstring.pack('uint:6', 32))  # Space
        
        # DTE (1 bit)
        bits.append(bitstring.pack('uint:1', 0))
        
        # Spare (1 bit)
        bits.append(bitstring.pack('uint:1', 0))
        
        return self._encode_payload(bits)

    def _encode_payload(self, bits):
        """
        Convert binary message to 6-bit ASCII payload
        """
        # Pad to multiple of 6 bits
        while len(bits) % 6:
            bits.append('0b0')
            
        # Convert 6-bit groups to ASCII characters
        payload = ''
        for i in range(0, len(bits), 6):
            sixbits = bits[i:i+6].uint
            if sixbits < 40:
                payload += chr(sixbits + 48)
            else:
                payload += chr(sixbits + 56)
                
        return payload
    
    def generate_position_report(self):
        """
        Generate complete NMEA AIVDM sentence
        """
        payload = self.encode_position_report()            
        # AIVDM,1,1,,A,payload,0
        checksum = self._calculate_checksum(f"AIVDM,1,1,,A,{payload},0")
        return f"!AIVDM,1,1,,A,{payload},0*{checksum}"
    
    def generate_static_data(self):
        """
        Generate complete NMEA AIVDM sentence
        """
        payload = self.encode_static_data()
        # AIVDM,1,1,,A,payload,0
        checksum = self._calculate_checksum(f"AIVDM,1,1,,A,{payload},0")
        return f"!AIVDM,1,1,,A,{payload},0*{checksum}"

    def _calculate_checksum(self, data):
        """
        Calculate the NMEA checksum
        """
        checksum = 0
        for char in data:
            checksum ^= ord(char)
        return format(checksum, '02X')

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
        """
        Send NMEA sentence with random corruption (10% chance)
        Types of corruption:
        1. Wrong checksum
        2. Non-printable characters (with correct checksum)
        """
        if not sentence.startswith("$"):
            sentence = "$" + sentence
            
        # chance of corruption
        should_corrupt = random.random() < 0.0
        
        if should_corrupt:
            corruption_type = random.choice(['checksum', 'non_printable'])
            
            if corruption_type == 'checksum':
                # Calculate correct checksum
                checksum = self.calculate_nmea_checksum(sentence)
                # Generate an incorrect checksum by adding 1 to the correct one
                wrong_checksum = f"{(int(checksum, 16) + 1) % 256:02X}"
                full_sentence = f"{sentence}*{wrong_checksum}\r\n"
                logging.info(f"Sending NMEA with corrupted checksum: {full_sentence.strip()}")
                
            else:  # non_printable
                # Insert a random non-printable character (ASCII 1-31)
                non_printable = chr(random.randint(1, 31))
                # Insert at random position after $ but before any potential *
                asterisk_pos = sentence.find('*')
                if asterisk_pos == -1:
                    asterisk_pos = len(sentence)
                insert_pos = random.randint(1, asterisk_pos - 1)
                corrupted_sentence = sentence[:insert_pos] + non_printable + sentence[insert_pos:]
                
                # Calculate checksum for the corrupted sentence
                checksum = self.calculate_nmea_checksum(corrupted_sentence)
                full_sentence = f"{corrupted_sentence}*{checksum}\r\n"
                logging.info(f"Sending NMEA with non-printable character at position {insert_pos}")
        else:
            # Normal case - correct sentence with valid checksum
            checksum = self.calculate_nmea_checksum(sentence)
            full_sentence = f"{sentence}*{checksum}\r\n"
            logging.info(f"Sending NMEA: {full_sentence.strip()}")

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

    def send_unsupported_message(self):
        """
        Send NMEA message which is unsupported by OpenCPN.
        """
        self.send_nmea("GPZZZ,A,B,C,D")

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
                speed_ms = vessel.speed * 0.514444
                
                # Calculate movement
                heading_rad = math.radians(vessel.course)
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
                pos_report = vessel.generate_position_report()
                logging.info(f"Sending NMEA: {pos_report.strip()}")
                self.sock.sendto(pos_report.encode(), (self.udp_host, self.udp_port))

                # Send static data
                static_data = vessel.generate_static_data()
                logging.info(f"Sending NMEA: {static_data.strip()}")
                self.sock.sendto(static_data.encode(), (self.udp_host, self.udp_port))
        
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
                "lat": parse_coordinate(wp["lat"]),
                "lon": parse_coordinate(wp["lon"]),
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
                self.send_unsupported_message()  # Unsupported message

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
            vessel_name="BAY TRADER",
            ship_type=AISVessel.SHIP_TYPES['CARGO'],
            position={"lat": "37° 40.3575' N", "lon": "122° 22.1460' W"},
            navigation_status=AISVessel.NAV_STATUS['UNDERWAY_ENGINE'],
            speed=12.0,
            course=270.0,
        ),
        AISVessel(
            mmsi=366123457,
            vessel_name="ANCHOR QUEEN",
            ship_type=AISVessel.SHIP_TYPES['TANKER'],
            position={"lat": "37° 40.4575' N", "lon": "122° 22.2460' W"},
            navigation_status=AISVessel.NAV_STATUS['AT_ANCHOR'],
            speed=0.0,
        ),
        AISVessel(
            mmsi=366123458,
            vessel_name="DISABLED LADY",
            ship_type=AISVessel.SHIP_TYPES['CARGO'],
            position={"lat": "37° 40.5575' N", "lon": "122° 22.3460' W"},
            navigation_status=AISVessel.NAV_STATUS['NOT_UNDER_COMMAND'],
            speed=0.1,
        ),
        AISVessel(
            mmsi=366123459,
            vessel_name="DREDGER ONE",
            ship_type=AISVessel.SHIP_TYPES['DREDGER'],
            position={"lat": "37° 40.6575' N", "lon": "122° 22.4460' W"},
            navigation_status=AISVessel.NAV_STATUS['RESTRICTED_MANEUVER'],
            speed=3.0,
        ),
        AISVessel(
            mmsi=366123460,
            vessel_name="DEEP DRAFT",
            ship_type=AISVessel.SHIP_TYPES['TANKER'],
            draft=15.5,
            position={"lat": "37° 40.7575' N", "lon": "122° 22.5460' W"},
            navigation_status=AISVessel.NAV_STATUS['CONSTRAINED_DRAFT'],
            speed=15.0,
        ),
        AISVessel(
            mmsi=366123461,
            vessel_name="PIER SIDE",
            ship_type=AISVessel.SHIP_TYPES['CARGO'],
            position={"lat": "37° 40.8575' N", "lon": "122° 22.6460' W"},
            navigation_status=AISVessel.NAV_STATUS['MOORED'],
            speed=0.0,
        ),
        AISVessel(
            mmsi=366123462,
            vessel_name="ON THE ROCKS",
            ship_type=AISVessel.SHIP_TYPES['CARGO'],
            position={"lat": "37° 40.9575' N", "lon": "122° 22.7460' W"},
            navigation_status=AISVessel.NAV_STATUS['AGROUND'],
            speed=15.0,
            course=50.0,
        ),
        AISVessel(
            mmsi=366123463,
            vessel_name="FISHING MASTER",
            ship_type=AISVessel.SHIP_TYPES['FISHING'],
            position={"lat": "37° 41.0575' N", "lon": "122° 22.8460' W"},
            navigation_status=AISVessel.NAV_STATUS['FISHING'],
            speed=4.5,
        ),
        AISVessel(
            mmsi=366123464,
            vessel_name="WIND WALKER",
            ship_type=AISVessel.SHIP_TYPES['SAILING'],
            position={"lat": "37° 40.3775' N", "lon": "122° 22.1460' W"},
            navigation_status=AISVessel.NAV_STATUS['UNDERWAY_SAILING'],
            speed=6.0,
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
