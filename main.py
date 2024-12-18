#!/usr/bin/env python3

import argparse
import logging
from datetime import timedelta

from src.simulator import BasicNavSimulator
from src.models.ais_vessel import AISVessel


def parse_log_level(level_str):
    """Convert string log level to logging constant."""
    level_str = level_str.upper()
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    if level_str not in levels:
        raise ValueError(
            f"Invalid log level: {level_str}. Must be one of {', '.join(levels.keys())}"
        )
    return levels[level_str]


def main():
    """Run the NMEA simulator with example configuration"""

    parser = argparse.ArgumentParser(description="NMEA Navigation Simulator")
    parser.add_argument(
        "--protocol",
        choices=["0183", "2000"],
        default="0183",
        help="NMEA protocol version",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host address for UDP messages"
    )
    parser.add_argument(
        "--port", type=int, default=10110, help="Port number for UDP messages"
    )
    parser.add_argument(
        "--loglevel",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level",
    )

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=parse_log_level(args.loglevel),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    # Create simulator instance
    simulator = BasicNavSimulator(
        host=args.host,
        port=args.port,
        protocol=args.protocol,
    )

    # Example waypoints for a route in San Francisco Bay
    waypoints = [
        {"lat": "37° 40.3574' N", "lon": "122° 22.1457' W"},
        {"lat": "37° 43.4444' N", "lon": "122° 20.7058' W"},
        {"lat": "37° 48.0941' N", "lon": "122° 22.7372' W"},
        {"lat": "37° 49.1258' N", "lon": "122° 25.2814' W"},
    ]

    speed_profile = [
        (timedelta(minutes=1), 8.0),
        (timedelta(minutes=4), 0.1),  # Stall for 2 minutes
        (timedelta(minutes=15), 10.0),
        (None, 8.0),
    ]

    # Create some example AIS vessels
    ais_vessels = [
        AISVessel(
            mmsi=366123456,
            vessel_name="BAY TRADER",
            ship_type=AISVessel.SHIP_TYPES["CARGO"],
            position={"lat": "37° 40.3575' N", "lon": "122° 22.1460' W"},
            navigation_status=AISVessel.NAV_STATUS["UNDERWAY_ENGINE"],
            speed=12.0,
            course=50.0,
        ),
        AISVessel(
            mmsi=366123457,
            vessel_name="ANCHOR QUEEN",
            ship_type=AISVessel.SHIP_TYPES["TANKER"],
            position={"lat": "37° 40.4575' N", "lon": "122° 22.2460' W"},
            navigation_status=AISVessel.NAV_STATUS["AT_ANCHOR"],
            speed=0.0,
        ),
        AISVessel(
            mmsi=366123458,
            vessel_name="DISABLED LADY",
            ship_type=AISVessel.SHIP_TYPES["CARGO"],
            position={"lat": "37° 40.5575' N", "lon": "122° 22.3460' W"},
            navigation_status=AISVessel.NAV_STATUS["NOT_UNDER_COMMAND"],
            speed=0.1,
        ),
        AISVessel(
            mmsi=366123459,
            vessel_name="DREDGER ONE",
            ship_type=AISVessel.SHIP_TYPES["DREDGER"],
            position={"lat": "37° 40.6575' N", "lon": "122° 22.4460' W"},
            navigation_status=AISVessel.NAV_STATUS["RESTRICTED_MANEUVER"],
            speed=3.0,
        ),
        AISVessel(
            mmsi=366123460,
            vessel_name="DEEP DRAFT",
            ship_type=AISVessel.SHIP_TYPES["TANKER"],
            draft=15.5,
            position={"lat": "37° 40.7575' N", "lon": "122° 22.5460' W"},
            navigation_status=AISVessel.NAV_STATUS["CONSTRAINED_DRAFT"],
            speed=15.0,
        ),
        AISVessel(
            mmsi=366123461,
            vessel_name="PIER SIDE",
            ship_type=AISVessel.SHIP_TYPES["CARGO"],
            position={"lat": "37° 40.8575' N", "lon": "122° 22.6460' W"},
            navigation_status=AISVessel.NAV_STATUS["MOORED"],
            speed=0.0,
        ),
        AISVessel(
            mmsi=366123462,
            vessel_name="ON THE ROCKS",
            ship_type=AISVessel.SHIP_TYPES["CARGO"],
            position={"lat": "37° 40.9575' N", "lon": "122° 22.7460' W"},
            navigation_status=AISVessel.NAV_STATUS["AGROUND"],
            speed=0.0,
        ),
        AISVessel(
            mmsi=366123463,
            vessel_name="FISHING MASTER",
            ship_type=AISVessel.SHIP_TYPES["FISHING"],
            position={"lat": "37° 41.0575' N", "lon": "122° 22.8460' W"},
            navigation_status=AISVessel.NAV_STATUS["FISHING"],
            speed=8.0,
            course=80.0,
        ),
        AISVessel(
            mmsi=366123464,
            vessel_name="WIND WALKER",
            ship_type=AISVessel.SHIP_TYPES["SAILING"],
            position={"lat": "37° 40.3775' N", "lon": "122° 22.1460' W"},
            navigation_status=AISVessel.NAV_STATUS["UNDERWAY_SAILING"],
            speed=6.0,
        ),
    ]

    logging.info("Starting simulation...")
    simulator.simulate(
        waypoints=waypoints,
        speed_profile=speed_profile,
        duration_seconds=None,
        update_rate=1,  # Update every second
        wind_direction=270,  # Wind coming from the west
        wind_speed=15.0,  # 15 knots of wind
        ais_vessels=ais_vessels,
    )


if __name__ == "__main__":
    main()
