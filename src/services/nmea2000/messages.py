from dataclasses import dataclass


@dataclass
class NMEA2000Message:
    """NMEA 2000 message structure"""

    pgn: int  # Parameter Group Number
    priority: int  # Priority (0-7)
    source: int  # Source address
    destination: int  # Destination address
    data: bytes  # Message data
