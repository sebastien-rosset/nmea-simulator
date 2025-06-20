#!/usr/bin/env python3

import argparse
import logging
import yaml
from datetime import timedelta
from typing import Dict, Any, Optional

from nmea_simulator.simulator import BasicNavSimulator
from nmea_simulator.models.ais_vessel import AISVessel


def parse_log_level(level_str: str) -> int:
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


def parse_timedelta(time_str: str) -> timedelta:
    """Parse time string in format 'Xm' or 'Xs' into timedelta."""
    if not time_str:
        return None
    unit = time_str[-1].lower()
    value = float(time_str[:-1])
    if unit == "m":
        return timedelta(minutes=value)
    elif unit == "s":
        return timedelta(seconds=value)
    raise ValueError(
        f"Invalid time format: {time_str}. Use 'm' for minutes or 's' for seconds"
    )


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def create_ais_vessel(vessel_config: Dict[str, Any]) -> AISVessel:
    """Create AIS vessel from configuration dictionary."""
    return AISVessel(
        mmsi=vessel_config["mmsi"],
        vessel_name=vessel_config["vessel_name"],
        ship_type=AISVessel.SHIP_TYPES[vessel_config["ship_type"]],
        position=vessel_config["position"],
        navigation_status=AISVessel.NAV_STATUS[vessel_config["navigation_status"]],
        speed=vessel_config.get("speed", 0.0),
        course=vessel_config.get("course", 0.0),  # Added default value of 0.0
        draft=vessel_config.get("draft"),
    )


def parse_speed_profile(profile_config: list) -> list:
    """Parse speed profile configuration."""
    return [
        (parse_timedelta(item["duration"]), item["speed"]) for item in profile_config
    ]


def main():
    """Run the NMEA simulator with YAML configuration"""
    parser = argparse.ArgumentParser(description="NMEA Navigation Simulator")
    parser.add_argument(
        "--config", required=True, help="Path to YAML configuration file"
    )
    # Optional command-line overrides
    parser.add_argument(
        "--nmea_version",
        choices=["0183", "2000"],
        help="Override NMEA protocol version",
    )
    parser.add_argument("--host", help="Override host address for UDP messages")
    parser.add_argument(
        "--port", type=int, help="Override port number for UDP messages"
    )
    parser.add_argument(
        "--network_protocol",
        choices=["UDP", "TCP"],
        help="Network protocol (UDP or TCP)",
    )
    parser.add_argument(
        "--loglevel",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override logging level",
    )
    parser.add_argument(
        "--duration",
        help="Override simulation duration (e.g., '30s', '5m')",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Command-line arguments override config file
    if args.host:
        config["host"] = args.host
    if args.port:
        config["port"] = args.port
    if args.nmea_version:
        config["nmea_version"] = args.nmea_version
    if args.network_protocol:
        config["network_protocol"] = args.network_protocol
    if args.loglevel:
        config["loglevel"] = args.loglevel
    if args.duration:
        config["duration"] = args.duration

    host = config.get("host")
    if host is None:
        host = "127.0.0.1" if config["network_protocol"] == "UDP" else "0.0.0.0"
    config["host"] = host

    # Set up logging
    logging.basicConfig(
        level=parse_log_level(config.get("loglevel", "INFO")),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    # Create simulator instance
    simulator = BasicNavSimulator(
        host=config.get("host"),
        port=config.get("port", 10110),
        nmea_version=config.get("nmea_version", "0183"),
        n2k_format=config.get("n2k_format"),
        exclude_sentences=config.get("exclude_sentences"),
        network_protocol=config.get("network_protocol", "UDP"),
    )

    # Create AIS vessels from configuration
    ais_vessels = [
        create_ais_vessel(vessel_config)
        for vessel_config in config.get("ais_vessels", [])
    ]

    # Parse speed profile
    speed_profile = parse_speed_profile(config["speed_profile"])

    # Extract heading fluctuations configuration
    heading_fluctuations = config.get("heading_fluctuations", {})

    # Parse duration if provided
    duration = None
    if config.get("duration"):
        duration = parse_timedelta(config["duration"])

    logging.info("Starting simulation...")
    simulator.simulate(
        waypoints=config["waypoints"],
        speed_profile=speed_profile,
        duration=duration,
        update_rate=config.get("update_rate", 1),
        wind_direction=config.get("wind_direction", 0),
        wind_speed=config.get("wind_speed", 0),
        ais_vessels=ais_vessels,
        heading_fluctuations=heading_fluctuations,
    )


if __name__ == "__main__":
    main()
