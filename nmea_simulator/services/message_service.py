from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from socket import socket, AF_INET, SOCK_DGRAM, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
import logging
import re
import threading
import time
from typing import Dict, Optional, Union, List

from nmea_simulator.models.route import Position, RouteManager
from .nmea2000 import NMEA2000Formatter, NMEA2000Message, MessageVerifier, PGN
from nmea_simulator.utils.coordinate_utils import (
    calculate_bearing,
    calculate_cross_track_error,
    calculate_distance,
)
from nmea_simulator.utils.navigation_utils import calculate_vmg


@dataclass
class WindData:
    apparent_speed: float  # knots
    apparent_angle: float  # degrees relative to bow (-180 to +180)


class NMEAVersion(Enum):
    """NMEA protocol version"""

    NMEA_0183 = "0183"
    NMEA_2000 = "2000"


class TransportProtocol(Enum):
    """Transport protocol for NMEA messages"""

    UDP = "UDP"
    TCP = "TCP"


class NMEA0183Formatter:
    """Formats messages according to NMEA 0183 standard"""

    def format_message(self, message: str) -> List[str]:
        """Format NMEA 0183 message with checksum"""
        if not message.startswith("$"):
            message = "$" + message

        checksum = self.calculate_checksum(message)
        formatted = f"{message}*{checksum}\r\n"
        return [formatted]

    def calculate_checksum(self, sentence: str) -> str:
        """Calculate NMEA 0183 checksum"""
        start = 1
        end = sentence.find("*")
        if end == -1:
            end = len(sentence)

        checksum = 0
        for char in sentence[start:end]:
            checksum ^= ord(char)

        return f"{checksum:02X}"


class MessageService:
    """Handles NMEA message formatting and sending"""

    def __init__(
        self,
        host: str = None,
        port: int = 10110,
        nmea_version: NMEAVersion = NMEAVersion.NMEA_0183,
        n2k_format: str = None,
        exclude_sentences: List[str] = None,
        network_protocol: TransportProtocol = TransportProtocol.UDP,
        talker_id: str = "GP",
    ):
        """
        Initialize the NMEA message service.

        This service handles formatting and sending NMEA messages over TCP or UDP.
        It supports both NMEA 0183 and NMEA 2000 protocols.

        Args:
            host: The IP address to use.
                - For UDP: Defaults to "127.0.0.1" (localhost)
                - For TCP: Defaults to "0.0.0.0" (all interfaces)
                For local testing, use localhost.
                For sending to other devices on the network, use their IP address.

            port: The port number to use. Defaults to 10110.
                - 10110 is the standard port for NMEA 0183 over TCP or UDP
                - For NMEA 2000, this port will receive the CAN frames.
                - The port must match the receiving application's configuration (e.g., OpenCPN)

            version: The NMEA protocol version to use. Defaults to NMEA 0183.
                    Determines how messages will be formatted:
                    - NMEA 0183: ASCII strings with checksum
                    - NMEA 2000: Binary CAN frames

            n2k_format: NMEA 2000 output format (only used when protocol is 2000).

            excluded_sentences: List of NMEA 0183 sentence types to exclude from sending.

            protocol: Transport protocol to use (UDP or TCP). Defaults to UDP.
                     For TCP, the service will listen for incoming connections.

            talker_id: Two-character talker ID to use in NMEA 0183 messages. Defaults to "GP".
                      Common talker IDs include:
                      - GP: Global Positioning System (GPS)
                      - GL: GLONASS
                      - GA: Galileo
                      - GB: BeiDou
                      - GN: Global Navigation Satellite System (GNSS)
                      - WI: Weather Instruments
                      - HE: Heading Equipment
                      - SD: Sounder/Depth Equipment
                      - VW: Velocity Sensor, Water referenced
                      - HC: Heading and Course Equipment

        Creates:
            - UDP socket for sending messages or TCP server for listening
            - Appropriate message formatter based on protocol version

        Note:
            The UDP socket is connectionless, so no connection needs to be established.
            Messages will be sent regardless of whether anything is listening on the target
            host:port combination.
        """
        # Set appropriate default host based on protocol
        self.host = host
        self.port = port
        self.protocol = network_protocol
        self.version = nmea_version
        self.client_sockets = []  # For TCP connections
        
        # Validate and store talker ID
        if len(talker_id) != 2 or not talker_id.isalpha():
            raise ValueError(f"Talker ID must be exactly 2 alphabetic characters, got: '{talker_id}'")
        self.talker_id = talker_id.upper()


        # Create appropriate socket type
        if network_protocol == TransportProtocol.UDP:
            self.sock = socket(AF_INET, SOCK_DGRAM)
        else:  # TCP
            self.sock = socket(AF_INET, SOCK_STREAM)
            self.sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            self.sock.bind((host, port))
            self.sock.listen(5)
            self.sock.setblocking(False)  # Non-blocking mode
            self._stop_accept_thread = False
            self._accept_thread = threading.Thread(target=self._accept_connections)
            self._accept_thread.daemon = True
            self._accept_thread.start()
            logging.info(f"TCP server listening on {host}:{port}")

        if nmea_version == NMEAVersion.NMEA_0183:
            self.formatter = NMEA0183Formatter()
            logging.info(
                f"Initialized NMEA message service for {nmea_version.value} over {network_protocol.value}"
            )
        else:
            self.formatter = NMEA2000Formatter(output_format=n2k_format)
            logging.info(
                f"Initialized NMEA message service for {nmea_version.value} over {network_protocol.value}. Format: {n2k_format}"
            )
        # All possible sentence types
        self.all_sentence_types = [
            "RMC",
            "GGA",
            "HDT",
            "HDM",
            "HDG",
            "DBT",
            "MWV",
            "XTE",
            "RMB",
            "VHW",
            "RSA",
            "MWD",
        ]

        # Set up sentence exclusion
        self.exclude_sentences = exclude_sentences or []

        # Validate excluded sentences
        invalid_sentences = set(self.exclude_sentences) - set(self.all_sentence_types)
        if invalid_sentences:
            raise ValueError(f"Invalid sentence types to exclude: {invalid_sentences}")

    def _should_send_sentence(self, message: str) -> bool:
        """
        Determine if a given sentence should be sent based on enabled sentences.

        Args:
            message: The NMEA message to check

        Returns:
            bool: True if the sentence should be sent, False otherwise
        """
        # Extract the sentence type (without talker ID)
        match = re.match(r"\$?[A-Z]{2}([A-Z]{3})", message)
        send = False
        sentence_type = None
        if match:
            sentence_type = match.group(1)
            send = sentence_type not in self.exclude_sentences
        return send

    def send_nmea(self, message: Union[str, NMEA2000Message]):
        """
        Send NMEA message(s) in appropriate format.

        Args:
            message: NMEA message to send (string for 0183, NMEA2000Message for 2000)
        """
        try:
            formatted_messages = self.formatter.format_message(message)

            # Skip processing if no messages
            if not formatted_messages:
                return

            for formatted_message in formatted_messages:
                if self.version == NMEAVersion.NMEA_2000:
                    self._send_nmea_2000_message(formatted_message, message)
                elif self.version == NMEAVersion.NMEA_0183:
                    self._send_nmea_0183_message(formatted_message, message)
                else:
                    raise ValueError(f"Unsupported NMEA version: {self.version}")

        except Exception as e:
            logging.error(f"Error sending NMEA message: {e}")
            raise

    def _send_nmea_2000_message(
        self, formatted_message: bytes, original_message: Union[str, NMEA2000Message]
    ):
        """Handle sending of a single NMEA 2000 message."""
        if self.formatter.output_format == "ACTISENSE_RAW_ASCII":
            # For ACTISENSE_RAW_ASCII, just encode and send the ASCII string
            data = formatted_message
            log_message = formatted_message.decode("ascii").strip()
        else:
            # Handle binary CAN frame formats
            data = formatted_message
            verifier = MessageVerifier()
            frame_info = verifier.verify_can_frame(data)
            log_message = (
                f"Sending PGN {frame_info['pgn']} "
                f"({PGN.get_description(frame_info['pgn'])}) Raw bytes: {data.hex()}"
            )
            if isinstance(original_message, str):
                log_message += f" Converted from {original_message.strip()}"

        if isinstance(original_message, str):
            if not self._should_send_sentence(original_message):
                return

        self._send_data(data, log_message)

    def _send_nmea_0183_message(
        self, formatted_message: str, original_message: Union[str, NMEA2000Message]
    ):
        """Handle sending of a single NMEA 0183 message."""
        if not isinstance(original_message, str):
            raise ValueError("Conversion from NMEA 2000 to 0183 not supported")

        data = formatted_message
        # Handle both bytes and string types for log_message
        if isinstance(formatted_message, bytes):
            log_message = formatted_message.decode('utf-8').strip()
        else:
            log_message = formatted_message.strip()

        if self._should_send_sentence(original_message):
            self._send_data(data, log_message)

    def _accept_connections(self):
        """Handle incoming TCP connections in a separate thread"""
        while not self._stop_accept_thread:
            try:
                client_sock, addr = self.sock.accept()
                client_sock.setblocking(False)
                self.client_sockets.append(client_sock)
                logging.info(f"New TCP client connected from {addr}")
            except BlockingIOError:
                time.sleep(0.1)
            except Exception as e:
                logging.error(f"Error accepting TCP connection: {e}")
                time.sleep(1)

    def _send_data(self, data: Union[bytes, str], log_message: str):
        """Send data over the socket with logging."""
        if isinstance(data, str):
            data = data.encode()

        if self.protocol == TransportProtocol.UDP:
            self.sock.sendto(data, (self.host, self.port))
        else:  # TCP
            # Send to all connected clients
            disconnected = []
            for client in self.client_sockets:
                try:
                    client.send(data)
                except (BrokenPipeError, ConnectionResetError):
                    disconnected.append(client)
                    logging.info("TCP client disconnected")

            # Remove disconnected clients
            for client in disconnected:
                self.client_sockets.remove(client)
                client.close()

        logging.debug(f"Send NMEA {self.version.value}: '{log_message}'")

    def send_wind_messages(
        self,
        true_wind_speed: float,
        true_wind_direction: float,
        wind_data: WindData,
        heading: float,
        variation: float,
    ):
        """
        Send all wind-related NMEA messages (MWV and MWD).

        Args:
            true_wind_speed: True wind speed in knots
            true_wind_direction: True wind direction in degrees (FROM)
            wind_data: Apparent wind calculations
            heading: Vessel heading in degrees true
            variation: Magnetic variation in degrees (East negative)
        """
        # Send MWV (Wind Speed and Angle) for both true and apparent wind
        self.send_mwv_true(true_wind_speed, true_wind_direction, heading)
        self.send_mwv_apparent(wind_data.apparent_speed, wind_data.apparent_angle)
        self.send_mwd(true_wind_speed, true_wind_direction, variation)

    def send_mwv_true(self, wind_speed: float, wind_direction: float, heading: float):
        """Send MWV sentence for true wind"""
        # Calculate relative angle to bow
        relative_angle = (wind_direction - heading) % 360
        if relative_angle > 180:
            relative_angle -= 360

        # Ensure angle is positive (0-360) for NMEA format
        if relative_angle < 0:
            relative_angle += 360

        mwv = (
            f"{self.talker_id}MWV,"
            f"{relative_angle:.1f},"  # Wind angle
            f"T,"  # Reference: T (True)
            f"{wind_speed:.1f},"  # Wind speed
            f"N,"  # Units: N for knots
            f"A"  # Status: A for valid data
        )
        self.send_nmea(mwv)

    def send_mwv_apparent(self, apparent_speed: float, apparent_angle: float):
        """Send MWV sentence for apparent wind"""
        # Ensure angle is positive (0-360) for NMEA format
        if apparent_angle < 0:
            apparent_angle += 360

        mwv = (
            f"{self.talker_id}MWV,"
            f"{apparent_angle:.1f},"  # Wind angle
            f"R,"  # Reference: R (Relative/Apparent)
            f"{apparent_speed:.1f},"  # Wind speed
            f"N,"  # Units: N for knots
            f"A"  # Status: A for valid data
        )
        self.send_nmea(mwv)

    def send_gga(
        self,
        position: Dict[str, float],
        gps_quality: int,
        satellites_in_use: int,
        hdop: float,
        altitude: float,
        geoid_separation: float,
        dgps_age: str,
        dgps_station: str,
    ):
        """
        Create and send a GGA (Global Positioning System Fix Data) sentence.

        Args:
            position: Dict with 'lat' and 'lon' keys in decimal degrees
            gps_quality: GPS Quality indicator (0-8)
                0 = Invalid
                1 = GPS fix
                2 = DGPS fix
                3 = PPS fix
                4 = Real Time Kinematic
                5 = Float RTK
                6 = Estimated (dead reckoning)
                7 = Manual input mode
                8 = Simulation mode
            satellites_in_use: Number of satellites in use (00-12)
            hdop: Horizontal dilution of precision
            altitude: Antenna altitude above mean sea level (meters)
            geoid_separation: Geoidal separation (meters)
            dgps_age: Age of DGPS data (empty if not using DGPS)
            dgps_station: DGPS station ID (empty if not using DGPS)
        """
        now = datetime.now(UTC)
        timestamp = now.strftime("%H%M%S.00")

        # Build the GGA sentence
        gga = (
            f"{self.talker_id}GGA,"
            f"{timestamp},"
            f"{self.format_lat(position['lat'])},"
            f"{self.format_lon(position['lon'])},"
            f"{gps_quality},"
            f"{satellites_in_use:02d},"  # 00-12 satellites, leading zero
            f"{hdop:.1f},"
            f"{altitude:.1f},M,"  # Altitude and units
            f"{geoid_separation:.1f},M,"  # Geoid separation and units
            f"{dgps_age},"  # DGPS age (empty if not used)
            f"{dgps_station}"  # DGPS station ID (empty if not used)
        )

        self.send_nmea(gga)

    def send_xte(self, route_manager: RouteManager, current_position: Position, send_mode_indicator: bool = True):
        """
        Create and send an XTE (Cross-Track Error) sentence.
        Format: $--XTE,A,A,x.x,L/R,N,A*hh

        Args:
            route_manager: Route manager containing current route segment
            current_position: Current vessel position

        The XTE sentence fields are:
            1. Cyclic Lock Status, A=valid, V = Loran-C Blink or SNR warning
            2. Signal Status, A=valid, V = Loran-C Cycle Lock warning flag
            3. Cross Track Error Magnitude
            4. Direction to steer, L or R
            5. Units, N=Nautical Miles
            6. FAA Mode Indicator (NMEA 2.3 and later, optional):
                A = Autonomous mode
                D = Differential mode
                E = Estimated (dead reckoning)
                M = Manual input
                S = Simulator
                N = Data not valid
        """
        # Get current segment
        segment = route_manager.get_current_segment()

        if segment is None:
            # No active segment, send zero XTE
            xte_magnitude = 0.0
            steer_direction = "L"
        else:
            # Calculate XTE for current segment
            xte_magnitude, steer_direction = calculate_cross_track_error(
                current_position.lat,
                current_position.lon,
                segment.start.lat,
                segment.start.lon,
                segment.end.lat,
                segment.end.lon,
            )

        # Build the XTE sentence (using NMEA 2.3 format with mode indicator)
        xte = (
            f"{self.talker_id}XTE,"
            f"A,A,"  # Both cyclic and signal status valid
            f"{xte_magnitude:.1f},"  # XTE magnitude
            f"{steer_direction},"  # Direction to steer (L/R)
            f"N"  # Units (Nautical Miles)
        )
        if send_mode_indicator:
            # Add mode indicator if requested
            xte += ",A"

        self.send_nmea(xte)

    def send_dbt(self, depth_meters: float):
        """
        Create and send a DBT (Depth Below Transducer) sentence.
        Converts the depth in meters to feet and fathoms and formats according to NMEA spec.

        Args:
            depth_meters: Depth below transducer in meters

        Format: $--DBT,x.x,f,x.x,M,x.x,F*hh
            - x.x,f = depth in feet
            - x.x,M = depth in meters
            - x.x,F = depth in fathoms
        """
        # Conversion factors
        METERS_TO_FEET = 3.28084
        METERS_TO_FATHOMS = 0.546807

        """
        DBT sentence fields are:
        1. Depth in feet
        2. f (feet)
        3. Depth in meters
        4. M (meters)
        5. Depth in fathoms
        6. F (fathoms)

        Example: $GPDBT,11.0,f,3.4,M,1.8,F*hh
        """
        # Convert depth to other units
        depth_feet = depth_meters * METERS_TO_FEET
        depth_fathoms = depth_meters * METERS_TO_FATHOMS

        # Build the DBT sentence with all three measurements
        dbt = (
            f"{self.talker_id}DBT,"
            f"{depth_feet:.1f},f,"  # Depth in feet
            f"{depth_meters:.1f},M,"  # Depth in meters
            f"{depth_fathoms:.1f},F"  # Depth in fathoms
        )

        self.send_nmea(dbt)

    def send_rsa(self, starboard_rudder: float, port_rudder: Optional[float] = None):
        """
        Create and send an RSA (Rudder Sensor Angle) sentence.
        Format: $--RSA,x.x,A,x.x,A*hh

        Args:
            starboard_rudder: Starboard (or single) rudder angle in degrees
                             (positive = starboard, negative = port)
            port_rudder: Optional port rudder angle for dual rudder vessels

        Note:
            Status field 'A' indicates valid data
            Status field 'V' would indicate invalid data
        """

        """
        RSA sentence fields are:
        1. Starboard (or single) rudder angle in degrees
        2. Status, A = valid data
        3. Port rudder angle in degrees
        4. Status, A = valid data

        Example for single rudder:  $HCRSA,10.5,A,,*hh
        Example for dual rudder:   $HCRSA,-5.2,A,-5.0,A*hh

        Positive angles = turn to starboard
        Negative angles = turn to port
        """
        if port_rudder is not None:
            # Dual rudder format
            rsa = (
                f"{self.talker_id}RSA,"
                f"{starboard_rudder:.1f},A,"  # Starboard rudder + status
                f"{port_rudder:.1f},A"  # Port rudder + status
            )
        else:
            # Single rudder format
            rsa = (
                f"{self.talker_id}RSA,"
                f"{starboard_rudder:.1f},A,"  # Single rudder + status
                f","  # Empty port rudder fields
            )

        self.send_nmea(rsa)

    def send_unsupported_message(self):
        """
        Send NMEA message which is unsupported by OpenCPN.
        """
        self.send_nmea(f"{self.talker_id}ZZZ,A,B,C,D")

    def send_vhw(self, heading: float, water_speed: float, variation: float):
        """
        Create a VHW (Water Speed and Heading) sentence.
        Format: $--VHW,x.x,T,x.x,M,x.x,N,x.x,K*hh

        Args:
            heading: True heading in degrees
            water_speed: Speed through water in knots
            variation: Magnetic variation in degrees (East negative)

        Note:
            - True heading and magnetic heading are both sent
            - Speed is sent in both knots and km/h
        """
        """
        VHW sentence fields are:
        1. Heading degrees true
        2. T = True
        3. Heading degrees magnetic
        4. M = Magnetic
        5. Speed knots
        6. N = Knots
        7. Speed kilometers per hour
        8. K = Kilometers per hour

        Example: $VWVHW,045.0,T,030.0,M,6.5,N,12.0,K*hh
        """

        # Calculate magnetic heading
        magnetic_heading = (heading + variation) % 360

        # Convert water speed to km/h
        speed_kmh = water_speed * 1.852  # 1 knot = 1.852 km/h

        # Build the VHW sentence
        vhw = (
            f"{self.talker_id}VHW,"
            f"{heading:.1f},T,"  # True heading
            f"{magnetic_heading:.1f},M,"  # Magnetic heading
            f"{water_speed:.1f},N,"  # Speed in knots
            f"{speed_kmh:.1f},K"  # Speed in km/h
        )

        self.send_nmea(vhw)

    def send_rmb(
        self, route_manager: RouteManager, current_position: Position, sog: float
    ):
        """
        Create and send an RMB (Recommended Minimum Navigation) sentence.
        Format: $--RMB,A,x.x,a,c--c,c--c,llll.ll,a,yyyyy.yy,a,x.x,x.x,x.x,A,A*hh

        Args:
            route_manager: Route manager containing waypoint information
            current_position: Current vessel position
            sog: Speed over ground in knots
        """
        """
        RMB sentence fields:
        1. Data Status (A = Valid, V = Invalid)
        2. Cross Track Error magnitude in nm
        3. Direction to steer (L/R)
        4. FROM Waypoint ID
        5. TO Waypoint ID
        6. Destination Waypoint Latitude
        7. N/S
        8. Destination Waypoint Longitude
        9. E/W
        10. Range to destination in nm
        11. Bearing to destination in degrees true
        12. Destination closing velocity in knots
        13. Arrival Status (A = Arrived, V = Not arrived)
        14. Mode indicator (A = Autonomous, D = Differential, E = Estimated,
                        M = Manual, S = Simulator, N = Data not valid)

        Example: $GPRMB,A,0.66,L,003,004,4917.24,N,12309.57,W,001.3,052.5,000.5,V,A*20
        """
        segment = route_manager.get_current_segment()

        if segment is None:
            # No active waypoint - send empty RMB
            rmb = (
                f"{self.talker_id}RMB,A,,"  # Status, no XTE
                f",,"  # No waypoint IDs
                f",,"  # No destination lat
                f",,"  # No destination lon
                f",,"  # No range
                f",,"  # No bearing
                f",,"  # No VMG
                f"V,N"  # Arrival not valid, data not valid
            )
        else:
            # Calculate XTE for current segment
            xte_magnitude, steer_direction = calculate_cross_track_error(
                current_position.lat,
                current_position.lon,
                segment.start.lat,
                segment.start.lon,
                segment.end.lat,
                segment.end.lon,
            )

            # Calculate range and bearing to destination
            distance = calculate_distance(
                current_position.lat,
                current_position.lon,
                segment.end.lat,
                segment.end.lon,
            )

            bearing = calculate_bearing(
                current_position.lat,
                current_position.lon,
                segment.end.lat,
                segment.end.lon,
            )

            # Calculate VMG (Velocity Made Good) towards waypoint
            vmg = calculate_vmg(sog, bearing, bearing)

            # Format waypoint coordinates for NMEA
            wp_lat = self.format_lat(segment.end.lat)
            wp_lon = self.format_lon(segment.end.lon)

            # Previous waypoint ID (if available)
            from_waypoint = (
                f"WP{route_manager.current_index-1:03d}"
                if route_manager.current_index > 0
                else ""
            )

            # Current waypoint ID
            to_waypoint = f"WP{route_manager.current_index:03d}"

            # Determine if we've arrived at waypoint
            arrival_status = "A" if distance < route_manager.waypoint_threshold else "V"

            # Build the RMB sentence
            rmb = (
                f"{self.talker_id}RMB,"
                f"A,"  # Data status (A=valid)
                f"{xte_magnitude:.1f},"  # Cross Track Error
                f"{steer_direction},"  # Direction to steer (L/R)
                f"{from_waypoint},"  # FROM Waypoint ID
                f"{to_waypoint},"  # TO Waypoint ID
                f"{wp_lat},"  # Destination Waypoint Latitude
                f"{wp_lon},"  # Destination Waypoint Longitude
                f"{distance:.1f},"  # Range to destination
                f"{bearing:.1f},"  # Bearing to destination
                f"{vmg:.1f},"  # Destination closing velocity (VMG)
                f"{arrival_status},"  # Arrival Status
                f"A"  # Navigation Status (A=valid)
            )

        self.send_nmea(rmb)

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
            f"{self.talker_id}MWV,"
            f"{relative_angle:.1f},"  # Wind angle
            f"{reference},"  # Reference: R (Relative/Apparent) or T (True)
            f"{wind_speed:.1f},"  # Wind speed
            f"N,"  # Units: N for knots
            f"A"  # Status: A for valid data
        )
        self.send_nmea(mwv)

    def send_mwd(
        self, true_wind_speed: float, true_wind_direction: float, variation: float
    ):
        """
        Send MWD (Wind Direction and Speed) sentence.
        Format: $--MWD,x.x,T,x.x,M,x.x,N,x.x,M*hh
        """

        """
        MWV sentence fields are:
        1. Wind angle (0-359)
        2. Reference (R = Relative/Apparent, T = True)
        3. Wind speed
        4. Wind speed units (N = knots)
        5. Status (A = valid)

        MWD sentence fields are:
        1. Wind direction in degrees true
        2. T (True)
        3. Wind direction in degrees magnetic
        4. M (Magnetic)
        5. Wind speed in knots
        6. N (knots)
        7. Wind speed in meters/second
        8. M (meters/second)

        Examples:
        $WIMWV,45.1,R,12.5,N,A*1B (Apparent wind)
        $WIMWV,235.5,T,14.2,N,A*24 (True wind)
        $WIMWD,235.5,T,220.5,M,14.2,N,7.3,M*52
        """
        # Calculate magnetic wind direction
        magnetic_wind_dir = (true_wind_direction + variation) % 360

        # Convert wind speed to m/s
        wind_speed_ms = true_wind_speed * 0.514444  # Convert knots to m/s

        mwd = (
            f"{self.talker_id}MWD,"
            f"{true_wind_direction:.1f},T,"  # True wind direction
            f"{magnetic_wind_dir:.1f},M,"  # Magnetic wind direction
            f"{true_wind_speed:.1f},N,"  # Wind speed in knots
            f"{wind_speed_ms:.1f},M"  # Wind speed in m/s
        )
        self.send_nmea(mwd)

    def send_essential_data(
        self,
        position: Dict[str, float],
        sog: float,
        cog: float,
        heading: float,
        variation: float,
    ):
        """
        Send essential navigation data messages (RMC, HDT, HDM, HDG).

        Args:
            position: Dict with 'lat' and 'lon' keys in decimal degrees
            sog: Speed over ground in knots
            cog: Course over ground in degrees true
            heading: Heading in degrees true
            variation: Magnetic variation in degrees (East negative)
        """
        now = datetime.now(UTC)
        timestamp = now.strftime("%H%M%S.00")
        date = now.strftime("%d%m%y")

        # RMC - Recommended Minimum Navigation Information
        rmc = (
            f"{self.talker_id}RMC,{timestamp},A,"
            f"{self.format_lat(position['lat'])},"
            f"{self.format_lon(position['lon'])},"
            f"{sog:.1f},{cog:.1f},{date},"
            f"{abs(variation):.1f},{'E' if variation >= 0 else 'W'},,A"
        )
        self.send_nmea(rmc)

        # HDT - Heading True from gyrocompass
        hdt = f"{self.talker_id}HDT,{heading:.1f},T"
        self.send_nmea(hdt)

        # HDM - Heading Magnetic from magnetic compass
        magnetic_heading = (heading + variation) % 360
        hdm = f"{self.talker_id}HDM,{magnetic_heading:.1f},M"
        self.send_nmea(hdm)

        # HDG - Heading with variation/deviation
        hdg = f"{self.talker_id}HDG,{heading:.1f},0.0,E,{abs(variation):.1f},W"
        self.send_nmea(hdg)

    def close(self):
        """Close all sockets"""
        if self.protocol == TransportProtocol.TCP:
            self._stop_accept_thread = True
            # Close all client connections
            if self._accept_thread.is_alive():
                self._accept_thread.join(timeout=1.0)
            for client in self.client_sockets:
                client.close()
            self.client_sockets.clear()
        self.sock.close()

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
