import logging
from typing import Union
from .messages import NMEA2000Message
from .converter import NMEA2000Converter
from .pgns import PGN


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

    def _convert_0183_to_2000(self, message: str) -> bytes:
        """Convert NMEA 0183 message to NMEA 2000 format"""
        try:
            msg_type = self._get_message_type(message)

            # Message type conversion mapping
            conversion_map = {
                "HDT": ("convert_heading_to_2000", PGN.VESSEL_HEADING),
                "HDM": ("convert_heading_to_2000", PGN.VESSEL_HEADING),
                "HDG": ("convert_heading_to_2000", PGN.VESSEL_HEADING),
                "RMC": (
                    "convert_rmc_to_2000",
                    [PGN.SYSTEM_TIME, PGN.POSITION_RAPID, PGN.COG_SOG_RAPID],
                ),
                "GGA": ("convert_gga_to_2000", PGN.GNSS_POSITION),
                "DBT": ("convert_dbt_to_2000", PGN.WATER_DEPTH),
                "MWV": ("convert_mwv_to_2000", PGN.WIND_DATA),
                "XTE": ("convert_xte_to_2000", PGN.XTE),
                "RMB": ("convert_rmb_to_2000", PGN.NAVIGATION_DATA),
                "VHW": ("convert_vhw_to_2000", PGN.SPEED),
                "RSA": ("convert_rsa_to_2000", PGN.RUDDER),
                "MWD": ("convert_mwd_to_2000", PGN.WIND_DATA),
            }

            if msg_type in conversion_map:
                converter_method, expected_pgns = conversion_map[msg_type]
                convert_func = getattr(self.converter, converter_method)

                # Handle special cases
                if msg_type == "MWV":
                    is_true = message.split(",")[2] == "T"
                    result = convert_func(message, is_true)
                else:
                    result = convert_func(message)

                # Handle both single messages and lists of messages
                if isinstance(result, list):
                    # For messages that return multiple PGNs (like RMC)
                    if not isinstance(expected_pgns, list):
                        raise ValueError(
                            f"Unexpected multiple messages from {msg_type}"
                        )

                    # Verify each message's PGN matches expected
                    for msg, expected_pgn in zip(result, expected_pgns):
                        if msg.pgn != expected_pgn:
                            raise ValueError(f"PGN mismatch for {msg_type}")

                    # Return the first message's data (we can only return one)
                    return result[0].data if result else b""
                else:
                    # For single message conversions
                    if isinstance(expected_pgns, list):
                        raise ValueError(f"Expected multiple messages from {msg_type}")

                    if result and result.pgn == expected_pgns:
                        return result.data
                    else:
                        raise ValueError(f"PGN mismatch for message type {msg_type}")
            else:
                if msg_type:
                    logging.debug(f"Ignoring unsupported message type: {msg_type}")
                return b""

        except Exception as e:
            logging.error(f"Error converting message {message}: {str(e)}")
            return b""

    def _format_2000_message(self, message: NMEA2000Message) -> bytes:
        """Format native NMEA 2000 message"""
        try:
            frame = bytearray()
            header = (message.priority << 26) | (message.pgn << 8) | message.source
            frame.extend(header.to_bytes(4, "big"))
            frame.extend(message.data)
            return bytes(frame)
        except Exception as e:
            logging.error(f"Error formatting NMEA 2000 message: {str(e)}")
            return b""
