"""Unit conversion utilities for aviation measurements.

Handles conversions between different units commonly used in aviation:
- Altitude: feet (ft), meters (m), flight levels (FL)
- Distance: nautical miles (nm), meters (m)
"""

from dataclasses import dataclass
from typing import Union, Optional
import logging

logger = logging.getLogger(__name__)


# Conversion constants
FEET_TO_METERS = 0.3048
METERS_TO_FEET = 1.0 / FEET_TO_METERS
NAUTICAL_MILES_TO_METERS = 1852.0
METERS_TO_NAUTICAL_MILES = 1.0 / NAUTICAL_MILES_TO_METERS
FLIGHT_LEVEL_TO_FEET = 100.0


@dataclass
class Altitude:
    """Represents an altitude with unit awareness.
    
    Can convert between feet, meters, and flight levels.
    
    Example:
        alt = Altitude.from_feet(5000)
        print(alt.to_meters())  # 1524.0
        print(alt.to_flight_level())  # 50.0
    """
    
    value: float
    unit: str  # 'ft', 'm', or 'FL'
    
    @classmethod
    def from_feet(cls, feet: float) -> 'Altitude':
        """Create altitude from feet."""
        return cls(value=feet, unit='ft')
    
    @classmethod
    def from_meters(cls, meters: float) -> 'Altitude':
        """Create altitude from meters."""
        return cls(value=meters, unit='m')
    
    @classmethod
    def from_flight_level(cls, fl: float) -> 'Altitude':
        """Create altitude from flight level."""
        return cls(value=fl, unit='FL')
    
    def to_feet(self) -> float:
        """Convert to feet."""
        if self.unit == 'ft':
            return self.value
        elif self.unit == 'm':
            return self.value * METERS_TO_FEET
        elif self.unit == 'FL':
            return self.value * FLIGHT_LEVEL_TO_FEET
        else:
            raise ValueError(f"Unknown unit: {self.unit}")
    
    def to_meters(self) -> float:
        """Convert to meters."""
        if self.unit == 'm':
            return self.value
        elif self.unit == 'ft':
            return self.value * FEET_TO_METERS
        elif self.unit == 'FL':
            return self.value * FLIGHT_LEVEL_TO_FEET * FEET_TO_METERS
        else:
            raise ValueError(f"Unknown unit: {self.unit}")
    
    def to_flight_level(self) -> float:
        """Convert to flight level."""
        if self.unit == 'FL':
            return self.value
        else:
            feet = self.to_feet()
            return feet / FLIGHT_LEVEL_TO_FEET


class UnitConverter:
    """Utility class for unit conversions."""
    
    @staticmethod
    def feet_to_meters(feet: float) -> float:
        """Convert feet to meters."""
        return feet * FEET_TO_METERS
    
    @staticmethod
    def meters_to_feet(meters: float) -> float:
        """Convert meters to feet."""
        return meters * METERS_TO_FEET
    
    @staticmethod
    def nautical_miles_to_meters(nm: float) -> float:
        """Convert nautical miles to meters."""
        return nm * NAUTICAL_MILES_TO_METERS
    
    @staticmethod
    def meters_to_nautical_miles(meters: float) -> float:
        """Convert meters to nautical miles."""
        return meters * METERS_TO_NAUTICAL_MILES
    
    @staticmethod
    def flight_level_to_feet(fl: float) -> float:
        """Convert flight level to feet.
        
        Example: FL100 = 10000 feet
        """
        return fl * FLIGHT_LEVEL_TO_FEET
    
    @staticmethod
    def feet_to_flight_level(feet: float) -> float:
        """Convert feet to flight level."""
        return feet / FLIGHT_LEVEL_TO_FEET
    
    @staticmethod
    def parse_altitude(value: str) -> Optional[Altitude]:
        """Parse altitude string with unit.
        
        Examples:
            "5000 ft" -> Altitude(5000, 'ft')
            "1500m" -> Altitude(1500, 'm')
            "FL100" -> Altitude(100, 'FL')
            "10000" -> Altitude(10000, 'ft')  # Default to feet
        
        Args:
            value: Altitude string with optional unit
            
        Returns:
            Altitude object or None if parsing fails
        """
        value = value.strip()
        
        # Check for flight level
        if value.upper().startswith('FL'):
            try:
                fl_value = float(value[2:].strip())
                return Altitude.from_flight_level(fl_value)
            except ValueError:
                logger.warning(f"Failed to parse flight level: {value}")
                return None
        
        # Check for explicit unit
        if value.endswith('m') or value.endswith('M'):
            try:
                m_value = float(value[:-1].strip())
                return Altitude.from_meters(m_value)
            except ValueError:
                logger.warning(f"Failed to parse meters: {value}")
                return None
        
        if value.lower().endswith('ft'):
            try:
                ft_value = float(value[:-2].strip())
                return Altitude.from_feet(ft_value)
            except ValueError:
                logger.warning(f"Failed to parse feet: {value}")
                return None
        
        # Default to feet
        try:
            ft_value = float(value)
            return Altitude.from_feet(ft_value)
        except ValueError:
            logger.warning(f"Failed to parse altitude: {value}")
            return None


# Backward compatibility functions
def ft2m(feet: float) -> float:
    """Convert feet to meters (backward compatibility)."""
    return UnitConverter.feet_to_meters(feet)


def m2ft(meters: float) -> float:
    """Convert meters to feet (backward compatibility)."""
    return UnitConverter.meters_to_feet(meters)


def nm2m(nm: float) -> float:
    """Convert nautical miles to meters (backward compatibility)."""
    return UnitConverter.nautical_miles_to_meters(nm)


def m2nm(meters: float) -> float:
    """Convert meters to nautical miles (backward compatibility)."""
    return UnitConverter.meters_to_nautical_miles(meters)
