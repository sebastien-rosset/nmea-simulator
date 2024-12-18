from dataclasses import dataclass
from .pgns import PGN


@dataclass
class NMEA2000Message:
    """NMEA 2000 message structure"""

    pgn: int  # Parameter Group Number
    priority: int  # Priority (0-7)
    source: int  # Source address
    destination: int  # Destination address
    data: bytes  # Message data

    def get_description(self) -> str:
        """Get human-readable description of the message type"""
        return PGN.get_description(self.pgn)

    def get_readable_fields(self) -> str:
        """
        Format message data in a human-readable way based on PGN type.
        Returns a string representation of the key fields.
        """
        try:
            # Import struct here to avoid circular imports
            import struct

            if self.pgn == PGN.VESSEL_HEADING:
                sid, ref, heading, dev, var = struct.unpack("<BBhhh", self.data)
                return f"Heading: {heading/10000:.1f}°"

            elif self.pgn == PGN.SPEED:
                sid, ref, stw, sog = struct.unpack("<BBhh", self.data)
                return f"STW: {stw/100:.1f}kts"

            elif self.pgn == PGN.WATER_DEPTH:
                sid, depth, offset, range = struct.unpack("<BLhH", self.data)
                return f"Depth: {depth/100:.1f}m"

            elif self.pgn == PGN.WIND_DATA:
                sid, ref, speed, angle = struct.unpack("<BBhh", self.data)
                return f"Speed: {speed/100:.1f}m/s, Angle: {angle/10000:.1f}°"

            elif self.pgn == PGN.XTE:
                sid, mode, reserved, xte, reserved2 = struct.unpack("<BBBii", self.data)
                return f"XTE: {xte/100:.2f}m"

            else:
                # For unknown or unhandled PGNs, show first few bytes as hex
                return "Data: " + " ".join([f"{b:02X}" for b in self.data[:8]])

        except Exception as e:
            return f"Error parsing data: {e}"
