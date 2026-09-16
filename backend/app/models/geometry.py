from pydantic import BaseModel

Position = tuple[float, float]
Ring = list[Position]
BBox = tuple[float, float, float, float]


class PointGeometry(BaseModel):
    type: str = "Point"
    coordinates: Position


class LineGeometry(BaseModel):
    type: str = "LineString"
    coordinates: list[Position]


class PolygonGeometry(BaseModel):
    type: str = "Polygon"
    coordinates: list[Ring]


Geometry = PointGeometry | LineGeometry | PolygonGeometry
