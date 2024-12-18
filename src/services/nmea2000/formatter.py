from typing import Union
from .messages import NMEA2000Message
from .converter import NMEA2000Converter


class NMEA2000Formatter:
    """Formats messages according to NMEA 2000 standard"""

    def __init__(self):
        self.converter = NMEA2000Converter()

    def format_message(self, message: Union[str, NMEA2000Message]) -> bytes:
        """Format NMEA 2000 message"""
        if isinstance(message, str):
            return self._convert_0183_to_2000(message)
        else:
            return self._format_2000_message(message)

    def _convert_0183_to_2000(self, message: str) -> bytes:
        """Convert NMEA 0183 message to NMEA 2000 format"""
        # Example conversion for common messages:
        if message.startswith("$GPRMC"):
            messages = self.converter.convert_rmc_to_2000(message)
            # For now, just return the first message's data
            return messages[0].data if messages else b""
        elif message.startswith("$GPGGA"):
            n2k_message = self.converter.convert_gga_to_2000(message)
            return n2k_message.data if n2k_message else b""
        elif message.startswith("$SDDBT"):
            n2k_message = self.converter.convert_dbt_to_2000(message)
            return n2k_message.data if n2k_message else b""
        elif message.startswith("$WIMWV"):
            is_true = message.split(",")[2] == "T"
            n2k_message = self.converter.convert_mwv_to_2000(message, is_true)
            return n2k_message.data if n2k_message else b""

        raise NotImplementedError(f"Conversion not implemented for: {message}")

    def _format_2000_message(self, message: NMEA2000Message) -> bytes:
        """Format native NMEA 2000 message"""
        # Create the CAN frame format
        # This is a simplified example - actual implementation would depend on hardware
        frame = bytearray()

        # Add header (29-bit identifier)
        header = (message.priority << 26) | (message.pgn << 8) | message.source
        frame.extend(header.to_bytes(4, "big"))

        # Add data
        frame.extend(message.data)

        return bytes(frame)
