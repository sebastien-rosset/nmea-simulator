import math
import logging
import bitstring
from datetime import datetime, UTC
from typing import List, Dict, Union
from ..utils.coordinate_utils import parse_coordinate


class AISVessel:
    """AIS Vessel class"""

    # AIS Navigation Status codes
    NAV_STATUS = {
        "UNDERWAY_ENGINE": 0,  # Under way using engine
        "AT_ANCHOR": 1,  # At anchor
        "NOT_UNDER_COMMAND": 2,  # Not under command
        "RESTRICTED_MANEUVER": 3,  # Restricted maneuverability
        "CONSTRAINED_DRAFT": 4,  # Constrained by draught
        "MOORED": 5,  # Moored
        "AGROUND": 6,  # Aground
        "FISHING": 7,  # Engaged in fishing
        "UNDERWAY_SAILING": 8,  # Under way sailing
    }
    # Ship Types (common ones)
    SHIP_TYPES = {
        "CARGO": 70,  # Cargo ship
        "TANKER": 80,  # Tanker
        "FISHING": 30,  # Fishing vessel
        "SAILING": 36,  # Sailing vessel
        "PILOT": 50,  # Pilot vessel
        "TUG": 52,  # Tug
        "PASSENGER": 60,  # Passenger ship
        "FERRY": 61,  # Ferry
        "DREDGER": 33,  # Dredger
    }

    def __init__(
        self,
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
        rot: float = 0.0,
    ):
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
        self.ship_type = ship_type or self.SHIP_TYPES["CARGO"]  # Default to cargo ship

        # Set reasonable defaults based on ship type
        if self.ship_type == self.SHIP_TYPES["SAILING"]:
            self.length = length or 15.0  # Default 15m sailing vessel
            self.beam = beam or 4.0  # Default 4m beam
            self.draft = min(draft or 2.1, 25.5)  # Default 2.1m draft
        elif self.ship_type == self.SHIP_TYPES["FISHING"]:
            self.length = length or 25.0  # Default 25m fishing vessel
            self.beam = beam or 8.0  # Default 8m beam
            self.draft = min(draft or 3.5, 25.5)  # Default 3.5m draft
        else:  # Cargo or other large vessels
            self.length = length or 200.0  # Default 200m vessel
            self.beam = beam or 30.0  # Default 30m beam
            self.draft = min(draft or 12.0, 25.5)  # Default 12m draft

        self.call_sign = (call_sign or f"V{self.mmsi % 1000000:06d}")[:7]
        self.course = course
        self.speed = speed
        self.rot = rot
        self.navigation_status = navigation_status

        # Parse position
        self.position = {}
        if position:
            try:
                self.position = {
                    "lat": parse_coordinate(position["lat"]),
                    "lon": parse_coordinate(position["lon"]),
                }
            except (KeyError, ValueError) as e:
                raise ValueError(f"Invalid position format: {position}") from e

    def update_position(self, delta_time: float):
        """
        Update vessel position based on course and speed

        Args:
            delta_time: Time elapsed since last update in seconds
        """
        if (
            not self.position or delta_time <= 0 or delta_time > 60
        ):  # Cap at 60 seconds max
            return

        # Convert speed to meters per second
        speed_ms = self.speed * 0.514444  # 1 knot = 0.514444 m/s

        # Calculate movement in meters
        heading_rad = math.radians(self.course)
        dx = speed_ms * math.sin(heading_rad) * delta_time
        dy = speed_ms * math.cos(heading_rad) * delta_time

        # Convert to coordinate changes
        R = 6371000.0  # Earth radius in meters
        lat_rad = math.radians(self.position["lat"])

        # Calculate position changes in degrees
        dlat = (dy / R) * (180.0 / math.pi)  # More direct conversion to degrees
        # Adjust longitude change based on latitude to account for meridian convergence
        dlon = (dx / (R * math.cos(lat_rad))) * (180.0 / math.pi)

        # Log before updating
        logging.debug(
            f"Updating position for vessel {self.mmsi}:"
            f"\n  Speed: {self.speed:.1f} knots"
            f"\n  Course: {self.course:.1f}°"
            f"\n  Delta time: {delta_time:.3f} seconds"
            f"\n  Movement: dx={dx:.2f}m, dy={dy:.2f}m"
            f"\n  Changes: dlat={dlat:.6f}°, dlon={dlon:.6f}°"
            f"\n  Current: {self.position['lat']:.6f}°N, {self.position['lon']:.6f}°W"
            f"\n  New pos: {self.position['lat'] + dlat:.6f}°N, {self.position['lon'] + dlon:.6f}°W"
        )

        # Update position
        self.position["lat"] += dlat
        self.position["lon"] += dlon

        # Normalize coordinates
        self.position["lat"] = max(-90, min(90, self.position["lat"]))
        self.position["lon"] = ((self.position["lon"] + 180) % 360) - 180

    def update_navigation_status(self):
        """Update navigation status based on vessel state"""
        # Example logic for automatic status updates
        if self.speed < 0.1:  # Almost stationary
            if self.navigation_status not in [
                self.NAV_STATUS["AT_ANCHOR"],
                self.NAV_STATUS["MOORED"],
                self.NAV_STATUS["AGROUND"],
            ]:
                self.navigation_status = self.NAV_STATUS["AT_ANCHOR"]
        elif self.speed > 0.1:  # Moving
            if self.ship_type == self.SHIP_TYPES["SAILING"]:
                self.navigation_status = self.NAV_STATUS["UNDERWAY_SAILING"]
            else:
                self.navigation_status = self.NAV_STATUS["UNDERWAY_ENGINE"]

    def generate_messages(self) -> List[str]:
        """
        Generate all AIS messages for this vessel

        Returns:
            List of NMEA formatted AIS messages
        """
        messages = []

        # Generate position report
        pos_report = self.generate_position_report()
        if pos_report:
            messages.append(pos_report)

        # Generate static data less frequently (every 6 minutes in real AIS)
        static_data = self.generate_static_data()
        if static_data:
            messages.append(static_data)

        return messages

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
        bits.append(bitstring.pack("uint:6", 1))

        # Repeat Indicator (2 bits)
        bits.append(bitstring.pack("uint:2", 0))

        # MMSI (30 bits)
        bits.append(bitstring.pack("uint:30", self.mmsi))

        # Navigation Status (4 bits)
        bits.append(bitstring.pack("uint:4", self.navigation_status))

        # Rate of Turn (8 bits)
        bits.append(bitstring.pack("int:8", self.encode_rate_of_turn()))

        # Speed Over Ground (10 bits) - in 0.1 knot steps
        speed_int = int(self.speed * 10)
        bits.append(bitstring.pack("uint:10", min(speed_int, 1023)))

        # Position Accuracy (1 bit) - 0 = low, 1 = high
        bits.append(bitstring.pack("uint:1", 0))

        # Convert coordinates to AIS format (in 1/10000 minute)
        # Ensure longitude is within valid range (-180 to 180)
        lon = ((self.position["lon"] + 180) % 360) - 180
        # Convert to AIS format
        lon_ais = int(lon * 600000)
        # Clamp to valid range for 28-bit signed integer
        lon_ais = max(-134217728, min(134217727, lon_ais))

        # Same for latitude (-90 to 90)
        lat = max(-90, min(90, self.position["lat"]))
        lat_ais = int(lat * 600000)
        # Clamp to valid range for 27-bit signed integer
        lat_ais = max(-67108864, min(67108863, lat_ais))

        # Longitude (28 bits) - in 1/10000 minute
        bits.append(bitstring.pack("int:28", lon_ais))

        # Latitude (27 bits) - in 1/10000 minute
        bits.append(bitstring.pack("int:27", lat_ais))

        # Course Over Ground (12 bits) - in 0.1 degree steps
        cog = int(self.course * 10)
        bits.append(bitstring.pack("uint:12", cog))

        # True Heading (9 bits) - use COG if not available
        bits.append(bitstring.pack("uint:9", int(self.course)))

        # Time Stamp (6 bits) - seconds of UTC timestamp
        timestamp = datetime.now(UTC).second
        bits.append(bitstring.pack("uint:6", timestamp))

        # Reserved (4 bits)
        bits.append(bitstring.pack("uint:4", 0))

        # Return the binary data encoded in 6-bit ASCII format
        return self._encode_payload(bits)

    def encode_static_data(self):
        """
        Encode Static and Voyage Related Data (Message Type 5)
        Uses 6-bit ASCII encoding as per ITU-R M.1371
        """
        bits = bitstring.BitArray()

        # Message Type (6 bits) - Type 5
        bits.append(bitstring.pack("uint:6", 5))

        # Repeat Indicator (2 bits)
        bits.append(bitstring.pack("uint:2", 0))

        # MMSI (30 bits)
        bits.append(bitstring.pack("uint:30", self.mmsi))

        # AIS Version (2 bits)
        bits.append(bitstring.pack("uint:2", 0))

        # IMO Number (30 bits) - Using 0 for this example
        bits.append(bitstring.pack("uint:30", 0))

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
            bits.append(bitstring.pack("uint:6", sixbit))

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
            bits.append(bitstring.pack("uint:6", sixbit))

        # Ship Type (8 bits)
        bits.append(bitstring.pack("uint:8", self.ship_type))

        # Dimension to Bow (9 bits)
        bits.append(bitstring.pack("uint:9", int(self.length / 2)))

        # Dimension to Stern (9 bits)
        bits.append(bitstring.pack("uint:9", int(self.length / 2)))

        # Dimension to Port (6 bits)
        bits.append(bitstring.pack("uint:6", int(self.beam / 2)))

        # Dimension to Starboard (6 bits)
        bits.append(bitstring.pack("uint:6", int(self.beam / 2)))

        # Draft (8 bits) - in 0.1 meter steps
        draft_dm = int(self.draft * 10)
        bits.append(bitstring.pack("uint:8", draft_dm))

        # Destination (120 bits) - 20 six-bit characters
        destination = "".ljust(20)
        for char in destination:
            bits.append(bitstring.pack("uint:6", 32))  # Space

        # DTE (1 bit)
        bits.append(bitstring.pack("uint:1", 0))

        # Spare (1 bit)
        bits.append(bitstring.pack("uint:1", 0))

        return self._encode_payload(bits)

    def _encode_payload(self, bits):
        """
        Convert binary message to 6-bit ASCII payload
        """
        # Pad to multiple of 6 bits
        while len(bits) % 6:
            bits.append("0b0")

        # Convert 6-bit groups to ASCII characters
        payload = ""
        for i in range(0, len(bits), 6):
            sixbits = bits[i : i + 6].uint
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
        return format(checksum, "02X")
