"""
VanCity Lens — Broadway Plan Vision Parser

Uses Gemini 1.5 Pro to extract geographic boundaries from
Broadway Plan PDF map images.

Strategy:
1. Convert PDF pages to high-res images (pdf2image)
2. Feed each map page to Gemini Vision with a structured prompt
3. Extract sub-area boundary polygons as coordinate arrays
4. Return ExtractedBoundary objects for downstream anchoring
"""

import json
import base64
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from PIL import Image

from .models import BroadwaySubArea, ExtractedBoundary

# Reference corners for geo-rectification of Broadway Plan maps.
# These are known landmarks visible in the PDF that we can use
# to transform pixel coordinates to WGS84 lat/lng.
REFERENCE_POINTS = {
    # (pixel_x, pixel_y) -> (lng, lat)
    "broadway_city_hall_station": {"lng": -123.1148, "lat": 49.2632},
    "commercial_broadway_station": {"lng": -123.0694, "lat": 49.2627},
    "arbutus_station": {"lng": -123.1530, "lat": 49.2632},
    "1st_and_vine": {"lng": -123.1416, "lat": 49.2720},
    "16th_and_main": {"lng": -123.1010, "lat": 49.2525},
}

# Broadway Plan approximate bounding box
BROADWAY_BBOX = {
    "west": -123.155,
    "east": -123.065,
    "north": 49.275,
    "south": 49.250,
}

VISION_PROMPT = """You are a geospatial data extraction specialist analyzing a map from the 
Vancouver Broadway Plan (2022). 

This map shows colored sub-areas of the Broadway Corridor between approximately:
- West: Vine Street (lng ~-123.155)
- East: Clark Drive (lng ~-123.065)  
- North: 1st Avenue (lat ~49.275)
- South: 16th Avenue (lat ~49.250)

Known reference points on this map:
- Broadway-City Hall Station: (-123.1148, 49.2632)
- Commercial-Broadway Station: (-123.0694, 49.2627)
- Arbutus Station: (-123.1530, 49.2632)

For EACH colored sub-area you can identify on the map, extract:
1. "sub_area": The sub-area label/code (C1, C2, C3, C4, Shoulder_North, Shoulder_South, Industrial, Residential_Transition)
2. "polygon": An array of [longitude, latitude] coordinate pairs tracing the boundary
3. "confidence": Your confidence in the boundary accuracy (0.0 to 1.0)

Use the reference station locations and street grid to estimate real-world coordinates.
Trace boundaries along street center-lines where possible.

Return ONLY valid JSON in this format:
{
  "boundaries": [
    {
      "sub_area": "C1",
      "polygon": [[-123.115, 49.264], [-123.110, 49.264], ...],
      "confidence": 0.7,
      "source_description": "Pink/magenta area around Broadway-City Hall station"
    }
  ]
}
"""


class BroadwayVisionParser:
    """Parses Broadway Plan PDF maps using Gemini Vision."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def _image_to_base64(self, img: Image.Image) -> str:
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    async def parse_map_page(
        self,
        image: Image.Image,
        page_number: int,
    ) -> list[ExtractedBoundary]:
        """
        Send a single map page image to Gemini Vision and extract boundaries.
        """
        b64 = self._image_to_base64(image)

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Content(
                    parts=[
                        types.Part(text=VISION_PROMPT),
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="image/png",
                                data=base64.b64decode(b64),
                            )
                        ),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,  # Low temp for structured extraction
                response_mime_type="application/json",
            ),
        )

        raw_text = response.text
        data = json.loads(raw_text)
        boundaries = []

        for item in data.get("boundaries", []):
            try:
                sub_area = BroadwaySubArea(item["sub_area"])
            except ValueError:
                continue  # Skip unknown sub-areas

            boundary = ExtractedBoundary(
                sub_area=sub_area,
                raw_polygon_coords=item["polygon"],
                source_page=page_number,
                confidence=item.get("confidence", 0.5),
            )
            boundaries.append(boundary)

        return boundaries

    async def parse_pdf(self, pdf_path: str) -> list[ExtractedBoundary]:
        """
        Full pipeline: PDF -> images -> Gemini Vision -> ExtractedBoundary list.
        Only processes pages that appear to contain maps (heuristic: large images).
        """
        from pdf2image import convert_from_path

        images = convert_from_path(
            pdf_path,
            dpi=300,
            fmt="png",
        )

        all_boundaries: list[ExtractedBoundary] = []

        for page_num, img in enumerate(images, start=1):
            # Heuristic: skip pages that are mostly text (small file size)
            # Map pages tend to be visually dense
            width, height = img.size
            if width < 1000 or height < 1000:
                continue

            print(f"  Processing page {page_num} ({width}x{height})...")
            boundaries = await self.parse_map_page(img, page_num)
            print(f"    Found {len(boundaries)} sub-area boundaries")
            all_boundaries.extend(boundaries)

        return all_boundaries
