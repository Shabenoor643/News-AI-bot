from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class VisionAnalysisResult(BaseModel):
    vehicle_visible: bool
    model_confirmed: Optional[str] = None
    primary_color: str
    body_style: str
    camera_angle: str
    notable_features: List[str] = []
    image_quality: str  # "good" | "partial" | "unusable"
    humans_present: bool
    is_cropped: bool
    background_type: str

class ImageValidationResult(BaseModel):
    humans_present: bool
    full_vehicle_visible: bool
    vehicle_cropped: bool
    background_clean: bool
    overall_pass: bool

class Entities(BaseModel):
    bike_models: List[str]
    brands: List[str]
    people: List[str]
    locations: List[str]
    dates: List[str]

class QuotedStatement(BaseModel):
    speaker: str
    quote: str

class FactExtractionResult(BaseModel):
    headline_summary: str
    key_facts: List[str]
    entities: Entities
    event_type: str
    quoted_statements: List[QuotedStatement]
    single_source_fields: List[str]

class ContentDraftAngle(BaseModel):
    type: str
    title: str
    meta_title: str
    meta_description: str
    keywords: List[str]
    slug: str
    article: str

class ContentDraft(BaseModel):
    articles: List[ContentDraftAngle]
