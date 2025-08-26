from dataclasses import dataclass

@dataclass
class Viewport:
    x: float
    y: float
    zoom: float

    @classmethod
    def default(cls) -> 'Viewport':
        return cls(
            x=38.4585561497326,
            y=232.49966577540107,
            zoom=0.21557486631016043
        )
