"""Configuration schema for friendliness index computation."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import json
from pathlib import Path


class KernelType(Enum):
    EXPONENTIAL = "exponential"
    POWER_LAW = "power_law"


@dataclass
class KernelConfig:
    kernel_type: KernelType = KernelType.EXPONENTIAL
    lambda_m: float = 300.0  # for exponential kernel
    p: float = 2.0  # for power law kernel
    d0_m: float = 50.0  # softening distance for power law


@dataclass
class GridConfig:
    cell_size_m: float = 50.0  # grid cell width in meters


@dataclass
class Config:
    kernel: KernelConfig = field(default_factory=KernelConfig)
    grid: GridConfig = field(default_factory=GridConfig)
    r_max_m: float = 1500.0  # max influence radius in meters
    tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    poi_config_path: str = "poi_config.json"

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        kernel_data = d.get("kernel", {})
        kernel_type = KernelType(kernel_data.get("kernel_type", "exponential"))
        kernel = KernelConfig(
            kernel_type=kernel_type,
            lambda_m=kernel_data.get("lambda_m", 300.0),
            p=kernel_data.get("p", 2.0),
            d0_m=kernel_data.get("d0_m", 50.0),
        )
        grid_data = d.get("grid", {})
        grid = GridConfig(
            cell_size_m=grid_data.get("cell_size_m", 50.0),
        )
        return cls(
            kernel=kernel,
            grid=grid,
            r_max_m=d.get("r_max_m", 1500.0),
            tile_url=d.get("tile_url", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
            poi_config_path=d.get("poi_config_path", "poi_config.json"),
        )

    def to_dict(self) -> dict:
        return {
            "kernel": {
                "kernel_type": self.kernel.kernel_type.value,
                "lambda_m": self.kernel.lambda_m,
                "p": self.kernel.p,
                "d0_m": self.kernel.d0_m,
            },
            "grid": {
                "cell_size_m": self.grid.cell_size_m,
            },
            "r_max_m": self.r_max_m,
            "tile_url": self.tile_url,
            "poi_config_path": self.poi_config_path,
        }


@dataclass
class BBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @classmethod
    def from_string(cls, s: str) -> "BBox":
        parts = [float(x.strip()) for x in s.split(",")]
        if len(parts) != 4:
            raise ValueError("BBox must be 4 comma-separated values: min_lon,min_lat,max_lon,max_lat")
        bbox = cls(*parts)
        bbox.validate()
        return bbox

    def validate(self) -> None:
        """Validate bbox coordinates and raise helpful errors for common mistakes."""
        # Check latitude bounds
        if not (-90 <= self.min_lat <= 90):
            raise ValueError(
                f"Invalid min_lat={self.min_lat}. Latitude must be between -90 and 90. "
                f"Did you swap lon/lat? Format is: min_lon,min_lat,max_lon,max_lat"
            )
        if not (-90 <= self.max_lat <= 90):
            raise ValueError(
                f"Invalid max_lat={self.max_lat}. Latitude must be between -90 and 90. "
                f"Did you swap lon/lat? Format is: min_lon,min_lat,max_lon,max_lat"
            )

        # Check longitude bounds
        if not (-180 <= self.min_lon <= 180):
            raise ValueError(
                f"Invalid min_lon={self.min_lon}. Longitude must be between -180 and 180."
            )
        if not (-180 <= self.max_lon <= 180):
            raise ValueError(
                f"Invalid max_lon={self.max_lon}. Longitude must be between -180 and 180."
            )

        # Check min < max
        if self.min_lon >= self.max_lon:
            raise ValueError(
                f"min_lon ({self.min_lon}) must be less than max_lon ({self.max_lon})"
            )
        if self.min_lat >= self.max_lat:
            raise ValueError(
                f"min_lat ({self.min_lat}) must be less than max_lat ({self.max_lat})"
            )

    def to_tuple(self) -> tuple:
        return (self.min_lon, self.min_lat, self.max_lon, self.max_lat)

    def buffer_degrees(self, meters: float, lat: Optional[float] = None) -> "BBox":
        """Buffer bbox by approximate meters (converted to degrees)."""
        if lat is None:
            lat = (self.min_lat + self.max_lat) / 2
        import math
        deg_per_m_lat = 1.0 / 111320.0
        deg_per_m_lon = 1.0 / (111320.0 * math.cos(math.radians(lat)))
        buffer_lat = meters * deg_per_m_lat
        buffer_lon = meters * deg_per_m_lon
        return BBox(
            min_lon=self.min_lon - buffer_lon,
            min_lat=self.min_lat - buffer_lat,
            max_lon=self.max_lon + buffer_lon,
            max_lat=self.max_lat + buffer_lat,
        )
