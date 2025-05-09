import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Literal, Optional, Tuple, Union

from nmea_simulator.utils.navigation_utils import (
    calculate_water_speed,
    update_vessel_position,
)
from nmea_simulator.utils.vessel_dynamics import RudderState
from nmea_simulator.utils.weather_utils import calculate_apparent_wind

from .models.ais_manager import AISManager, AISVessel
from .models.environment import EnvironmentManager
from .models.route import RouteManager, Position
from .models.speed_profile import SpeedManager
from .services.message_service import MessageService, NMEAVersion, TransportProtocol
from .utils.coordinate_utils import parse_coordinate


class BasicNavSimulator:
    """
    Marine navigation simulator that generates NMEA messages.
    Coordinates various subsystems to simulate vessel movement and conditions.
    """

    def __init__(
        self,
        host:str=None,
        port:int=10110,
        nmea_version: Literal["0183", "2000"] = "0183",
        n2k_format: str = None,
        exclude_sentences: Optional[List[str]] = None,
        network_protocol: Literal["2000", "0183"] = "0183",
    ):
        """
        Initialize simulator with network settings and subsystems.

        Args:
            host: Host address for UDP messages
            port: Port number for UDP messages
            version: NMEA protocol version ("0183" or "2000")
            n2k_format: NMEA 2000 output format
            exclude_sentences: Optional list of NMEA sentence types to exclude
        """

        nmea_version = (
            NMEAVersion.NMEA_0183 if nmea_version == "0183" else NMEAVersion.NMEA_2000
        )
        network_protocol = (
            TransportProtocol.UDP
            if network_protocol == "UDP"
            else TransportProtocol.TCP
        )
        # Initialize managers and services
        self.message_service = MessageService(
            host,
            port,
            nmea_version=nmea_version,
            n2k_format=n2k_format,
            exclude_sentences=exclude_sentences,
            network_protocol=network_protocol,
        )
        self.route_manager = RouteManager()
        self.speed_manager = SpeedManager()
        self.environment_manager = EnvironmentManager()
        self.ais_manager = AISManager()

        # Vessel state
        self.position = {"lat": 0, "lon": 0}
        self.sog = None  # Speed over ground in knots
        self.cog = 0.0  # Course over ground in degrees true
        self.heading = 0.0  # Heading in degrees true
        self.water_speed = 0.0  # Speed through water in knots

        # Vessel configuration
        self.variation = -15.0  # Magnetic variation (East negative)
        self.starboard_rudder = 0.0  # Angle in degrees, negative = port
        self.port_rudder = 0.0  # For dual rudder vessels
        self.max_rudder_angle = 35.0  # Maximum rudder deflection
        self.has_dual_rudder = False

        # Instrument state
        self.gps_quality = 1  # GPS fix
        self.satellites_in_use = 8
        self.hdop = 1.0
        self.altitude = 0.0
        self.geoid_separation = 0.0
        self.dgps_age = ""
        self.dgps_station = ""
        self.depth = 10.0  # Depth in meters

    def simulate(
        self,
        waypoints: List[Dict[str, Union[str, float]]],
        speed_profile: List[Tuple[Union[timedelta, None], float]],
        duration_seconds: Optional[float] = None,
        update_rate: float = 1,
        wind_direction: float = 0.0,
        wind_speed: float = 0.0,
        ais_vessels: Optional[List[AISVessel]] = None,
    ):
        """
        Run the navigation simulation.

        Args:
            waypoints: List of waypoint dictionaries with 'lat' and 'lon' keys
            speed_profile: List of (duration, speed) tuples defining vessel speed
            duration_seconds: Optional simulation duration in seconds
            update_rate: How often to update simulation state (seconds)
            wind_direction: True wind direction (FROM) in degrees
            wind_speed: True wind speed in knots
            ais_vessels: Optional list of AIS vessels to simulate
        """
        if not waypoints:
            raise ValueError("Must provide at least one waypoint")

        # Initialize subsystems
        self._initialize_simulation(
            waypoints, speed_profile, wind_direction, wind_speed, ais_vessels
        )

        # Main simulation loop
        start_time = time.time()
        last_update = start_time

        try:
            while True:
                current_time = time.time()

                # Check duration
                if (
                    duration_seconds is not None
                    and (current_time - start_time) >= duration_seconds
                ):
                    logging.info("Simulation duration reached")
                    break

                # Update simulation state
                if not self._update_simulation_state(current_time, last_update):
                    break

                # Send NMEA messages
                self._send_nmea_messages()

                last_update = current_time
                time.sleep(update_rate)

        except KeyboardInterrupt:
            logging.info("Simulation stopped by user")

    def _initialize_simulation(
        self,
        waypoints: List[Dict[str, Union[str, float]]],
        speed_profile: List[Tuple[Union[timedelta, None], float]],
        wind_direction: float,
        wind_speed: float,
        ais_vessels: Optional[List[AISVessel]],
    ):
        """Initialize all simulation subsystems"""
        # Parse and set waypoints
        parsed_waypoints = [
            {"lat": parse_coordinate(wp["lat"]), "lon": parse_coordinate(wp["lon"])}
            for wp in waypoints
        ]

        self.route_manager.set_waypoints(parsed_waypoints)
        self.position = {
            "lat": parsed_waypoints[0]["lat"],
            "lon": parsed_waypoints[0]["lon"],
        }

        # Initialize other subsystems
        self.speed_manager.set_speed_profile(speed_profile)
        self.sog = self.speed_manager.current_speed

        self.environment_manager.set_wind(wind_speed, wind_direction)

        if ais_vessels:
            self.ais_manager.add_vessels(ais_vessels)

    def _update_simulation_state(self, current_time: float, last_update: float) -> bool:
        """
        Update simulation state for current time step.

        Returns:
            bool: True if simulation should continue
        """
        delta_time = current_time - last_update

        # Update vessel speed
        self.sog = self.speed_manager.update_speed(current_time)

        # Update navigation
        current_pos = Position(lat=self.position["lat"], lon=self.position["lon"])
        continue_nav, desired_course = self.route_manager.update_course_to_waypoint(
            current_pos
        )

        if not continue_nav:
            logging.info("Navigation complete or error")
            return False

        # Update vessel position and dynamics with the desired course
        environment = self.environment_manager.environment
        new_position, new_cog, new_heading, new_rudder = update_vessel_position(
            self.position,
            RudderState(
                starboard_angle=self.starboard_rudder,
                port_angle=self.port_rudder,
                max_angle=self.max_rudder_angle,
                has_dual_rudder=self.has_dual_rudder,
            ),
            self.heading,
            desired_course,  # Use the desired course from route manager
            self.sog,
            environment.current.speed,
            environment.current.direction,
            delta_time,
        )

        # Update vessel state
        self.position = new_position
        self.cog = new_cog
        self.heading = new_heading
        self.starboard_rudder = new_rudder
        if self.has_dual_rudder:
            self.port_rudder = new_rudder

        # Calculate water speed
        water_speed_vector = calculate_water_speed(
            self.sog, self.cog, environment.current.speed, environment.current.direction
        )
        self.water_speed = water_speed_vector.speed

        # Update AIS
        self.ais_manager.update_vessels(
            current_time,
            self.message_service,
        )

        # Log current state
        self._log_state()
        return True

    def _send_nmea_messages(self):
        """Send all NMEA messages for current state"""
        # Convert position dict to Position object
        current_position = Position(lat=self.position["lat"], lon=self.position["lon"])

        self.message_service.send_essential_data(
            self.position, self.sog, self.cog, self.heading, self.variation
        )

        self.message_service.send_gga(
            self.position,
            self.gps_quality,
            self.satellites_in_use,
            self.hdop,
            self.altitude,
            self.geoid_separation,
            self.dgps_age,
            self.dgps_station,
        )

        self.message_service.send_dbt(self.depth)

        self.message_service.send_xte(self.route_manager, current_position)

        self.message_service.send_rmb(self.route_manager, current_position, self.sog)

        self.message_service.send_vhw(self.heading, self.water_speed, self.variation)

        self.message_service.send_rsa(self.starboard_rudder, self.port_rudder)

        # Wind messages
        environment = self.environment_manager.environment
        wind_data = calculate_apparent_wind(
            environment.wind.speed, environment.wind.direction, self.sog, self.heading
        )

        self.message_service.send_wind_messages(
            environment.wind.speed,  # true wind speed
            environment.wind.direction,  # true wind direction
            wind_data,  # apparent wind data
            self.heading,  # vessel heading
            self.variation,  # magnetic variation
        )

    def _log_state(self):
        """Log current simulation state"""
        logging.info(
            f"Position: {self.position['lat']:.6f}, {self.position['lon']:.6f}. "
            f"Heading: {self.heading:.2f}°. "
            f"Distance to WP: {self.route_manager.get_distance_to_next_waypoint(Position(**self.position)):.3f}nm. "
            f"SOG: {self.sog:.2f}kts"
        )

    def __del__(self):
        """Cleanup network resources"""
        self.message_service.close()
