import logging
import time
from typing import List, Union, Optional
from .messages import NMEA2000Message
from .converter import NMEA2000Converter
from .verifier import verify_pgn_conversion
from .pgns import PGN

# See OpenCPN/model/src/comm_drv_n2k_net.cpp
# CommDriverN2KNet::OnSocketEvent() for details
N2K_YD_RAW = "YD_RAW"  # RX Byte compatible with Actisense ASCII RAW
N2K_ACTISENSE_RAW_ASCII = "ACTISENSE_RAW_ASCII"
N2K_ACTISENSE_N2K_ASCII = "ACTISENSE_N2K_ASCII"
N2K_ACTISENSE_N2K = "ACTISENSE_N2K"
N2K_ACTISENSE_RAW = "ACTISENSE_RAW"
N2K_ACTISENSE_NGT = "ACTISENSE_NGT"
N2K_SEASMART = "SEASMART"
N2K_MINIPLEX = "MINIPLEX"


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

    def format_message(
        self, message: Union[str, NMEA2000Message, List[NMEA2000Message]]
    ) -> List[bytes]:
        """Format NMEA 2000 message(s) into a list of formatted byte messages.

        Args:
            message: Input message(s) to format. Can be:
                - NMEA 0183 string to convert and format
                - Single NMEA 2000 message
                - List of NMEA 2000 messages

        Returns:
            List of formatted messages as bytes. Empty list if no valid messages.
        """
        if isinstance(message, str):
            nmea2000_msg = self._convert_0183_to_2000(message)
        else:
            nmea2000_msg = message

        # Return empty if no message
        if not nmea2000_msg:
            return []

        # Handle single message
        if isinstance(nmea2000_msg, NMEA2000Message):
            return [self._format_single_message(nmea2000_msg)]

        # Handle list of messages
        if isinstance(nmea2000_msg, list):
            return [self._format_single_message(msg) for msg in nmea2000_msg]

        raise ValueError(f"Unexpected message type: {type(nmea2000_msg)}")

    def _format_single_message(self, nmea2000_msg: NMEA2000Message) -> bytes:
        """Format a single NMEA 2000 message"""
        msg: bytes = None
        if self.output_format == N2K_ACTISENSE_RAW_ASCII:
            msg = self.convert_to_actisense_raw_ascii(
                nmea2000_msg.pgn, nmea2000_msg.source, nmea2000_msg.data
            )
        elif self.output_format == N2K_YD_RAW:
            # See OpenCPN/model/src/comm_drv_n2k_net.cpp. CommDriverN2KNet::OnSocketEvent() for details
            # YD_RAW is a RX Byte compatible with Actisense ASCII RAW.
            msg = self.convert_to_actisense_raw_ascii(
                nmea2000_msg.pgn, nmea2000_msg.source, nmea2000_msg.data
            )
        elif self.output_format == N2K_ACTISENSE_N2K_ASCII:
            msg = self.convert_to_actisense_n2k_ascii(
                nmea2000_msg.pgn, nmea2000_msg.source, nmea2000_msg.data
            )
        elif self.output_format == N2K_ACTISENSE_N2K:
            raise NotImplementedError("ACTISENSE_N2K format not yet supported")
        elif self.output_format == N2K_ACTISENSE_NGT:
            raise NotImplementedError("ACTISENSE_NGT format not yet supported")
        elif self.output_format == N2K_SEASMART:
            raise NotImplementedError("SEASMART format not yet supported")
        elif self.output_format == N2K_MINIPLEX:
            raise NotImplementedError("MINIPLEX format not yet supported")
        else:
            raise ValueError(f"Unsupported output format: {self.output_format}")
        logging.info(f"Message PGN {nmea2000_msg.pgn}: {msg}")
        return msg

    def convert_to_actisense_raw_ascii(
        self, pgn, source, data, priority=6, destination=255, is_transmit=False
    ) -> bytes:
        """
        Convert CAN frame to Actisense RAW ASCII format compatible with OpenCPN

        Args:
        - pgn: Parameter Group Number
        - source: Source address of the device
        - data: List of bytes representing the message payload
        - priority: Message priority (default 6)
        - destination: Destination address (default 255 for broadcast)
        - is_transmit: Whether this is a transmit message (default False)

        Returns:
        Formatted Actisense RAW ASCII message
        """
        # Convert data to list of bytes if it's not already
        if isinstance(data, bytes):
            data = list(data)

        # Pad or truncate data to 8 bytes
        data_bytes = (data + [0] * 8)[:8]

        # Calculate CAN ID according to NMEA 2000 / ISO 11783-3 specification
        can_id = (
            (priority & 0x7) << 26
            | ((pgn >> 8) & 0x1FF) << 16  # PDU Format (full 9 bits)
            | (pgn & 0xFF) << 8  # PDU Specific
            | (source & 0xFF)  # Source address
        )

        # Format timestamp
        timestamp = time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000 % 1000):03d}"

        # Transmission flag
        tx_flag = "T" if is_transmit else "R"

        # Format the message according to OpenCPN's expected format:
        # HH:MM:SS.mmm R 18F11200 08 FF 00 00 00 00 00 00
        message = (
            f"{timestamp} {tx_flag} {can_id:08X} "
            + " ".join(f"{byte:02X}" for byte in data_bytes)
            + "\r\n"
        )

        # Detailed debug logging
        return message.encode("ascii")

    def convert_to_actisense_n2k_ascii(
        self, pgn, source, data, priority=6, destination=255
    ) -> bytes:
        """
        Convert CAN frame to Actisense N2K ASCII format bytes for OpenCPN

        Format: A<timestamp> <source><dest><priority> <pgn> <data>
        Example: A155950.886 01FF6 F1120 08FF00000000000000

        Args:
        - pgn: Parameter Group Number
        - source: Source address of the device
        - data: Bytes or list of bytes representing the message payload
        - priority: Message priority (default 6)
        - destination: Destination address (default 255 for broadcast)

        Returns:
        Bytes of the formatted Actisense N2K ASCII message
        """
        # Convert data to list of bytes if it's not already
        if isinstance(data, bytes):
            data = list(data)

        # Format timestamp
        timestamp = time.strftime("%H%M%S.") + f"{int(time.time() * 1000 % 1000):03d}"

        # Format source/dest/priority field
        field1 = f"{source:02X}{destination:02X}{priority:01X}"

        # Format data as hex string
        data_hex = "".join(f"{b:02X}" for b in data)

        # Build complete message
        message = f"A{timestamp} {field1} {pgn:05X} {data_hex}\r\n"

        logging.debug(f"Formatted N2K ASCII message: {message.strip()}")
        return message.encode("ascii")

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
