from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional, Tuple, Union
import logging
import time


@dataclass
class SpeedSegment:
    """Represents a speed segment with duration and target speed"""

    duration: Optional[timedelta]  # None means infinite duration
    speed: float  # Target speed in knots


@dataclass
class SpeedState:
    """Current speed state"""

    speed: float  # Current speed in knots
    segment_index: int  # Current segment index
    segment_start_time: Optional[float]  # Start time of current segment


class SpeedManager:
    """Manages vessel speed profiles and updates"""

    def __init__(self):
        """Initialize speed manager"""
        self._speed_profile: List[SpeedSegment] = []
        self._current_segment = 0
        self._segment_start_time: Optional[float] = None
        self._current_speed = 0.0

    def set_speed_profile(self, profile: List[Tuple[Union[timedelta, None], float]]):
        """
        Set the speed profile for the vessel.

        Args:
            profile: List of tuples (duration, speed)
                    duration: timedelta or None (None means infinite duration)
                    speed: Target speed in knots
        """
        # Convert profile to SpeedSegments
        self._speed_profile = [SpeedSegment(duration=d, speed=s) for d, s in profile]
        self._current_segment = 0
        self._segment_start_time = None

        # Set initial speed
        if self._speed_profile:
            self._current_speed = self._speed_profile[0].speed

        logging.info(f"Speed profile set with {len(self._speed_profile)} segments")

    def update_speed(self, current_time: float) -> float:
        """
        Update vessel speed based on the current profile segment.

        Args:
            current_time: Current simulation time in seconds

        Returns:
            float: Current speed in knots
        """
        if not self._speed_profile or self._current_segment >= len(self._speed_profile):
            return self._current_speed

        # Initialize segment start time if needed
        if self._segment_start_time is None:
            self._segment_start_time = current_time
            self._current_speed = self._speed_profile[self._current_segment].speed
            logging.info(
                f"Starting speed segment {self._current_segment}: "
                f"{self._current_speed} knots"
            )
            return self._current_speed

        current_segment = self._speed_profile[self._current_segment]
        elapsed_time = current_time - self._segment_start_time

        # Check if we need to move to the next segment
        if current_segment.duration is not None:
            if elapsed_time >= current_segment.duration.total_seconds():
                self._current_segment += 1
                self._segment_start_time = current_time

                # Update speed if there's a next segment
                if self._current_segment < len(self._speed_profile):
                    self._current_speed = self._speed_profile[
                        self._current_segment
                    ].speed
                    logging.info(
                        f"Changing to speed segment {self._current_segment}: "
                        f"{self._current_speed} knots"
                    )

        return self._current_speed

    @property
    def current_speed(self) -> float:
        """Get current speed in knots"""
        return self._current_speed

    @property
    def current_segment(self) -> Optional[SpeedSegment]:
        """Get current speed segment if available"""
        if not self._speed_profile or self._current_segment >= len(self._speed_profile):
            return None
        return self._speed_profile[self._current_segment]

    def get_state(self) -> SpeedState:
        """Get current speed state"""
        return SpeedState(
            speed=self._current_speed,
            segment_index=self._current_segment,
            segment_start_time=self._segment_start_time,
        )
