from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, NamedTuple


class SpeedSegment(NamedTuple):
    """Represents a speed segment with duration and target speed"""

    duration: Optional[timedelta]
    speed: float
