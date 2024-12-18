from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.utils.coordinate_utils import calculate_bearing, calculate_distance


@dataclass
class Waypoint:
    """Single waypoint in a route"""

    lat: float  # Latitude in decimal degrees
    lon: float  # Longitude in decimal degrees
    name: Optional[str] = None


@dataclass
class RouteSegment:
    """Represents a segment between two waypoints"""

    start: Waypoint
    end: Waypoint
    distance: float  # Distance in nautical miles
    bearing: float  # Initial bearing in degrees true


@dataclass
class Position:
    """Current position"""

    lat: float
    lon: float


class RouteManager:
    """Manages route waypoints and navigation state"""

    def __init__(self, waypoint_threshold: float = 0.1):
        """
        Args:
            waypoint_threshold: Distance in nautical miles to consider waypoint reached
        """
        self.waypoints: List[Waypoint] = []
        self.current_index: int = 0
        self.waypoint_threshold = waypoint_threshold
        self.reverse_direction = False

    def set_waypoints(self, waypoints: List[Dict[str, float]]):
        """Set route waypoints from list of lat/lon dictionaries"""
        self.waypoints = [Waypoint(lat=wp["lat"], lon=wp["lon"]) for wp in waypoints]
        self.current_index = 1 if len(self.waypoints) > 1 else 0
        self.reverse_direction = False

    def get_current_segment(self) -> Optional[RouteSegment]:
        """Get current route segment if available"""
        if self.current_index == 0 or self.current_index >= len(self.waypoints):
            return None

        start = self.waypoints[self.current_index - 1]
        end = self.waypoints[self.current_index]

        distance = calculate_distance(start.lat, start.lon, end.lat, end.lon)

        bearing = calculate_bearing(start.lat, start.lon, end.lat, end.lon)

        return RouteSegment(start, end, distance, bearing)

    def get_distance_to_next_waypoint(self, current_position: Position) -> float:
        """
        Calculate distance between current position and next waypoint.

        Args:
            current_position: Current vessel position

        Returns:
            float: Distance in nautical miles (0 if no active waypoint)
        """
        if self.current_index >= len(self.waypoints):
            return 0.0

        next_waypoint = self.waypoints[self.current_index]
        return calculate_distance(
            current_position.lat,
            current_position.lon,
            next_waypoint.lat,
            next_waypoint.lon,
        )

    def update_course_to_waypoint(
        self, current_position: Position
    ) -> Tuple[bool, Optional[float]]:
        """
        Update course to head towards the current waypoint.

        Args:
            current_position: Current vessel position

        Returns:
            Tuple[bool, Optional[float]]:
                - bool: True if navigation should continue
                - float: New course to steer (None if no valid course)
        """
        if not self.waypoints:
            return False, None

        next_waypoint = self.waypoints[self.current_index]

        # Calculate distance and bearing to next waypoint
        distance = self.get_distance_to_next_waypoint(current_position)

        # If we're close enough to waypoint, move to next one
        if distance < self.waypoint_threshold:
            if self.reverse_direction:
                self.current_index -= 1
                if self.current_index < 0:
                    self.current_index = 1
                    self.reverse_direction = False
            else:
                self.current_index += 1
                if self.current_index >= len(self.waypoints):
                    self.current_index = len(self.waypoints) - 2
                    self.reverse_direction = True

            # Recursively update for new waypoint
            return self.update_course_to_waypoint(current_position)

        # Calculate new course to waypoint
        new_course = calculate_bearing(
            current_position.lat,
            current_position.lon,
            next_waypoint.lat,
            next_waypoint.lon,
        )

        return True, new_course

    def update_progress(self, current_lat: float, current_lon: float) -> bool:
        """
        Update route progress based on current position.

        Args:
            current_lat: Current latitude in decimal degrees
            current_lon: Current longitude in decimal degrees

        Returns:
            bool: True if navigation should continue, False if route complete
        """
        segment = self.get_current_segment()
        if not segment:
            return False

        # Calculate distance to next waypoint
        distance = calculate_distance(
            current_lat, current_lon, segment.end.lat, segment.end.lon
        )

        # Check if waypoint reached
        if distance < self.waypoint_threshold:
            if self.reverse_direction:
                self.current_index -= 1
                if self.current_index < 0:
                    self.current_index = 1
                    self.reverse_direction = False
            else:
                self.current_index += 1
                if self.current_index >= len(self.waypoints):
                    self.current_index = len(self.waypoints) - 2
                    self.reverse_direction = True

        return True
