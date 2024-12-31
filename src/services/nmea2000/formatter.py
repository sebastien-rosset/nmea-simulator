import logging
from typing import Union, Optional
from .messages import NMEA2000Message
from .converter import NMEA2000Converter
from .verifier import verify_pgn_conversion
from .pgns import PGN

N2K_ACTISENSE_RAW_ASCII = "ACTISENSE_RAW_ASCII"  # aka YD_RAW https://www.yachtd.com/downloads/ydnr02.pdf appendix E
N2K_ACTISENSE_N2K_ASCII = "ACTISENSE_N2K_ASCII"
N2K_SEASMART = "SEASMART"
N2K_MINIPLEX = "MINIPLEX"
N2K_CAN = "CAN"


class NMEA2000Formatter:
    """Formats messages according to NMEA 2000 standard"""

    def __init__(self, output_format=None):
        """
        Initialize formatter with specified output format.

        Args:
            output_format: One of "ACTISENSE_RAW_ASCII", "ACTISENSE_N2K_ASCII", or "MINIPLEX"
        """
        self.converter = NMEA2000Converter()
        if output_format is None:
            output_format = N2K_ACTISENSE_RAW_ASCII
        self.output_format = output_format

    def format_message(self, message: Union[str, NMEA2000Message]) -> bytes:
        """Format NMEA 2000 message"""
        if isinstance(message, str):
            nmea2000_msg = self._convert_0183_to_2000(message)
        else:
            nmea2000_msg = message
        # Then format according to the output format
        if not nmea2000_msg:
            return b""
        if self.output_format == N2K_ACTISENSE_RAW_ASCII:
            return self._format_actisense_raw_ascii(
                nmea2000_msg.priority,
                nmea2000_msg.pgn,
                nmea2000_msg.source,
                nmea2000_msg.data,
            )
        elif self.output_format == N2K_CAN:
            return self._format_2000_message(nmea2000_msg)
        else:
            raise ValueError(f"Unsupported output format: {self.output_format}")

    def _format_actisense_raw_ascii(
        self, priority: int, pgn: int, source: int, data: bytes
    ) -> bytes:
        """
        Format message in YD RAW format
        Format: <timestamp> R <canid> <data bytes>
        Example: 12:35:45.123 R 0FF0103 01 C4 F6 E7 00 B4 23 55
        """
        from datetime import datetime

        # Extract PDU Format and Specific
        pf = (pgn >> 8) & 0xFF
        ps = pgn & 0xFF

        # In OpenCPN:
        # unsigned long can_id = BuildCanID(6, 0xff, 0xff, pgn);
        # Which expands to:
        # Build 29-bit ID according to ISO 11783:
        # * Bit 0-7  Source Address     (8 bits)
        # * Bit 8-15 PDU Specific (PS)  (8 bits)
        # * Bit 16-23 PDU Format (PF)   (8 bits)
        # * Bit 24-26 Priority          (3 bits)
        # * Bit 27-28 Reserved bit == 0 (2 bits)
        # * Bit 28 Data Page == 0       (1 bit)
        # Construct CAN ID
        can_id = (
            (priority & 0x7) << 26  # Priority (3 bits)
            | pf << 16  # PDU Format (8 bits)
            | ps << 8  # PDU Specific (8 bits)
            | source  # Source Address (8 bits)
        )

        # Format timestamp
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Format CAN ID as hex
        can_id_hex = f"{can_id:08X}"

        # Format data bytes as hex
        data_hex = " ".join([f"{b:02X}" for b in data])

        # Construct complete message
        msg = f"{timestamp} R {can_id_hex} {data_hex}\r\n"

        return msg.encode()

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

    def _convert_0183_to_2000(self, message: str) -> Optional[NMEA2000Message]:
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
                    for nmea2000_msg in result:
                        verify_pgn_conversion(message, nmea2000_msg)
                    return result[0] if result else None
                else:
                    verify_pgn_conversion(message, result)
                    return result
            else:
                if msg_type:
                    logging.error(f"Ignoring unsupported message type: {msg_type}")
                return None

        except Exception as e:
            logging.error(f"Error converting message {message}: {str(e)}")
            return None

    def _format_2000_message(self, message: NMEA2000Message) -> bytes:
        """
        Format a complete NMEA 2000 message for CAN frame transmission.

        Args:
            message: NMEA2000Message containing PGN, priority, addresses and data

        Returns:
            bytes: Complete frame in CAN format
        """
        try:
            # Validate ranges
            if not 0 <= message.priority <= 7:
                raise ValueError(f"Priority must be 0-7, got {message.priority}")
            if not 0 <= message.source <= 255:
                raise ValueError(f"Source address must be 0-255, got {message.source}")

            logging.debug(
                f"Formatting NMEA 2000 Message: PGN {message.pgn}, Priority {message.priority}, "
                f"Source {message.source}, Destination {message.destination}, "
                f"Data Length {len(message.data)}"
            )

            # Extract PDU Format (PF) - upper byte of PGN
            pf = (message.pgn >> 8) & 0xFF

            # Determine PDU Specific (PS) field
            if pf < 240:  # PDU1 format
                ps = message.destination
            else:  # PDU2 format
                ps = message.pgn & 0xFF

            data_length = len(message.data)
            if data_length <= 8:
                # Single frame message
                return self._format_single_frame(
                    message.priority, pf, ps, message.source, message.data
                )
            else:
                # Fast Packet Protocol for messages > 8 bytes
                return self._format_fast_packet(
                    message.priority, pf, ps, message.source, message.data
                )

        except Exception as e:
            logging.error(f"Error formatting NMEA 2000 message: {str(e)}")
            raise

    def _format_single_frame(
        self, priority: int, pf: int, ps: int, source: int, data: bytes
    ) -> bytes:
        """
        Format a single frame NMEA 2000 message with correct CAN ID construction.
        Modified to match OpenCPN's expected format.

        Args:
            priority: Message priority (0-7)
            pf: PDU Format (upper byte of original PGN)
            ps: PDU Specific (lower byte of PGN or destination)
            source: Source address
            data: Message payload

        Returns:
            bytes: Complete CAN frame
        """
        # Construct CAN ID using the NMEA 2000 / ISO 11783 specification
        can_id = (
            (priority & 0x7) << 26  # Priority (3 bits)
            | (pf & 0xFF) << 16  # PDU Format (8 bits)
            | (ps & 0xFF) << 8  # PDU Specific (8 bits)
            | (source & 0xFF)  # Source Address (8 bits)
        )

        frame = bytearray()

        # Add CAN ID using little-endian byte order (changed from big-endian)
        frame.extend(can_id.to_bytes(4, "little"))

        # Add length byte
        frame.append(len(data))

        # Add data
        frame.extend(data)

        # Enhanced debug logging
        logging.debug(f"CAN Frame Construction Details:")
        logging.debug(f"  CAN ID: {hex(can_id)}")
        logging.debug(f"  Priority: {priority}")
        logging.debug(f"  PDU Format (PF): {pf}")
        logging.debug(f"  PDU Specific (PS): {ps}")
        logging.debug(f"  Source Address: {source}")
        logging.debug(f"  Data Length: {len(data)}")
        logging.debug(f"  Raw Bytes: {frame.hex()}")

        return bytes(frame)

    def _format_fast_packet(
        self, priority: int, pf: int, ps: int, source: int, data: bytes
    ) -> bytes:
        """Format a Fast Packet Protocol message (for messages > 8 bytes)"""
        frames = []
        total_length = len(data)
        sequence = 0  # Sequence counter for this message

        # First frame
        frame_data = bytearray(
            [sequence, total_length]
        )  # First two bytes are sequence and length
        frame_data.extend(data[0:6])  # First 6 bytes of data
        frames.append(self._format_single_frame(priority, pf, ps, source, frame_data))

        # Subsequent frames
        pos = 6
        sequence = 1
        while pos < total_length:
            frame_data = bytearray([sequence])  # First byte is sequence
            chunk = data[pos : pos + 7]  # Up to 7 bytes per subsequent frame
            frame_data.extend(chunk)
            frames.append(
                self._format_single_frame(priority, pf, ps, source, frame_data)
            )
            pos += 7
            sequence += 1

        # Combine all frames
        return b"".join(frames)
