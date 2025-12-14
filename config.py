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
    n_target: int = 40000  # target max grid points
    s_min: float = 15.0  # minimum spacing in meters
    s_max: float = 75.0  # maximum spacing in meters


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
            n_target=grid_data.get("n_target", 40000),
            s_min=grid_data.get("s_min", 15.0),
            s_max=grid_data.get("s_max", 75.0),
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
                "n_target": self.grid.n_target,
                "s_min": self.grid.s_min,
                "s_max": self.grid.s_max,
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
        return cls(*parts)

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
