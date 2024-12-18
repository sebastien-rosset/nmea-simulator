import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class RudderState:
    """Container for rudder state information"""

    starboard_angle: float  # degrees
    port_angle: float  # degrees
    max_angle: float  # maximum deflection in degrees
    has_dual_rudder: bool


@dataclass
class VesselDynamics:
    """Container for vessel dynamics calculations"""

    heading: float  # degrees true
    turn_rate: float  # degrees per second


def update_rudder_angle(
    current_rudder: float,
    desired_heading: float,
    current_heading: float,
    max_rudder_angle: float,
    delta_time: float,
) -> float:
    """
    Update rudder angle based on desired vs current heading.
    Simple P controller for rudder adjustment.

    Args:
        current_rudder: Current rudder angle in degrees
        desired_heading: Target heading in degrees
        current_heading: Current vessel heading in degrees
        max_rudder_angle: Maximum rudder deflection in degrees
        delta_time: Time step in seconds

    Returns:
        float: New rudder angle in degrees
    """
    # Calculate heading error (-180 to +180 degrees)
    error = (desired_heading - current_heading + 180) % 360 - 180

    # Simple proportional control
    P_GAIN = 2.0
    desired_rudder = P_GAIN * error

    # Limit rudder angle to maximum deflection
    desired_rudder = max(-max_rudder_angle, min(max_rudder_angle, desired_rudder))

    # Apply rudder movement rate limit (typical 2.5-3 degrees per second)
    MAX_RATE = 3.0  # degrees per second
    max_change = MAX_RATE * delta_time

    if abs(desired_rudder - current_rudder) <= max_change:
        new_rudder = desired_rudder
    else:
        # Move towards desired angle at maximum rate
        new_rudder = current_rudder + (
            max_change if desired_rudder > current_rudder else -max_change
        )

    return new_rudder


def calculate_vessel_dynamics(
    heading: float, rudder_angle: float, max_rudder_angle: float, delta_time: float
) -> VesselDynamics:
    """
    Calculate vessel dynamics based on rudder angle.

    Args:
        heading: Current vessel heading in degrees
        rudder_angle: Current rudder angle in degrees
        max_rudder_angle: Maximum rudder deflection in degrees
        delta_time: Time step in seconds

    Returns:
        VesselDynamics: New heading and turn rate
    """
    # Rudder effect on turn rate
    RUDDER_TURN_RATE = 1.0  # degrees per second at full rudder
    turn_rate = (rudder_angle / max_rudder_angle) * RUDDER_TURN_RATE

    # Update heading based on rudder
    new_heading = (heading + turn_rate * delta_time) % 360

    return VesselDynamics(new_heading, turn_rate)
