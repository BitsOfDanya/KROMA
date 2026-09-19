export type Position = [number, number];
export type BBox = [number, number, number, number];

export type IncidentStatus = "suspected" | "confirmed" | "monitoring" | "localized";
export type Severity = "critical" | "high" | "medium" | "low";
export type ForecastLevel = "p50" | "p80" | "p95";
export type RiskObjectKind = "settlement" | "power_line" | "road" | "infrastructure" | "protected_area";
export type ObservationClass = "incident" | "persistent_source" | "unassigned";
export type BurnSeverity = "low" | "moderate" | "high";
export type TimelineEventKind =
  | "detected"
  | "observation"
  | "confirmed"
  | "priority_changed"
  | "perimeter_updated"
  | "forecast_issued"
  | "weather_updated"
  | "status_changed";

export interface Region {
  id: string;
  name: string;
  short_name: string;
  bbox: BBox;
  center: Position;
  zoom: number;
}

export interface IncidentCounts {
  active: number;
  critical: number;
  new_24h: number;
  confirmed: number;
  suspected: number;
  monitoring: number;
}

export interface Overview {
  generated_at: string;
  reference_time: string;
  data_source: "demo";
  regions: Region[];
  default_region_id: string;
  counts: IncidentCounts;
  observations_24h: number;
  raw_detections_7d: number;
  last_observation_at: string | null;
  top_incident_id: string | null;
}

export interface IncidentSnapshot {
  observed_at: string;
  status: IncidentStatus;
  confidence: number;
  threat: number;
  priority: number;
  area_ha: number;
  frp_mw: number;
  observation_count: number;
}

export interface SpreadEstimate {
  direction_deg: number;
  speed_m_per_h: number;
  wind_from_deg: number;
  wind_speed_ms: number;
}

export interface IncidentSummary {
  id: string;
  status: IncidentStatus;
  severity: Severity;
  region_id: string;
  region: string;
  district: string;
  centroid: Position;
  bbox: BBox;
  first_detected_at: string;
  confirmed_at: string | null;
  updated_at: string;
  is_new: boolean;
  confidence: number;
  threat: number;
  priority: number;
  area_ha: number;
  frp_mw: number;
  observation_count: number;
  nearest_settlement: { name: string; distance_km: number } | null;
  spread: SpreadEstimate;
  snapshots: IncidentSnapshot[];
}

export interface IncidentList {
  items: IncidentSummary[];
  total: number;
  counts: IncidentCounts;
  generated_at: string;
}

export interface EvidenceItem {
  code: string;
  label: string;
  detail: string;
  effect: "raises" | "lowers";
  strength: "strong" | "moderate" | "weak";
}

export interface RiskExposure {
  object_id: string;
  kind: RiskObjectKind;
  name: string;
  subtitle: string;
  population: number | null;
  distance_km: number;
  forecast_level: ForecastLevel | null;
}

export interface SatellitePass {
  id: string;
  incident_id: string;
  satellite: string;
  instrument: string;
  kind: "thermal" | "optical";
  resolution_m: number;
  overpass_at: string;
  cloud_probability: number | null;
  coverage: BBox;
}

export interface IncidentDetail extends IncidentSummary {
  landcover: string;
  ignition_point: Position;
  evidence: EvidenceItem[];
  exposures: RiskExposure[];
  next_passes: SatellitePass[];
  perimeter: { observed_at: string; source: string; area_ha: number; front_length_km: number } | null;
  forecast: { level: ForecastLevel; area_ha: number; horizon_hours: number; issued_at: string }[];
  burn_scar_id: string | null;
  weather?: {
    temperature_c: number;
    relative_humidity_pct: number;
    slope_deg: number;
    source: "scenario";
  } | null;
}

export interface TimelineEvent {
  id: string;
  incident_id: string | null;
  occurred_at: string;
  kind: TimelineEventKind;
  title: string;
  detail: string;
}

export interface IncidentTimeline {
  incident_id: string;
  events: TimelineEvent[];
  snapshots: IncidentSnapshot[];
  perimeters: { observed_at: string; valid_until: string | null; area_ha: number; source: string }[];
  passes: SatellitePass[];
}

export interface TimelineResponse {
  start: string;
  end: string;
  events: TimelineEvent[];
}

export interface Geometry {
  type: "Point" | "LineString" | "Polygon" | "MultiPolygon";
  coordinates: unknown;
}

export interface Feature<P = Record<string, unknown>> {
  type: "Feature";
  id?: string | number | null;
  geometry: Geometry;
  properties: P;
}

export interface FeatureCollection<P = Record<string, unknown>> {
  type: "FeatureCollection";
  features: Feature<P>[];
  meta: { count: number; crs: "EPSG:4326"; aggregated: boolean };
}

export interface HotspotProperties {
  t: number;
  incident_id: string | null;
  classification: ObservationClass | "aggregate";
  satellite?: string;
  instrument?: string;
  frp_mw: number;
  brightness_k?: number;
  confidence?: "l" | "n" | "h";
  daynight?: "D" | "N";
  pixel_size_m?: number;
  count?: number;
}

export interface SeverityBreakdown {
  low_ha: number;
  moderate_ha: number;
  high_ha: number;
}

export interface BurnScarSummary {
  id: string;
  incident_id: string | null;
  name: string;
  region_id: string;
  region: string;
  district: string;
  centroid: Position;
  bbox: BBox;
  fire_started_on: string;
  fire_ended_on: string | null;
  assessed_at: string;
  assessment: "final" | "preliminary";
  area_ha: number;
  dnbr_mean: number;
  severity: SeverityBreakdown;
}

export interface ImageryScene {
  satellite: string;
  product: string;
  acquired_on: string;
  cloud_cover_pct: number;
  scene_id: string;
}

export interface BurnScar extends Omit<BurnScarSummary, "severity"> {
  landcover: string;
  geometry: Geometry;
  zones: { severity: BurnSeverity; area_ha: number; geometry: Geometry }[];
  before: ImageryScene;
  after: ImageryScene;
}

export interface BurnScarList {
  items: BurnScarSummary[];
  total: number;
}

export interface AnalyticsSummary {
  start: string;
  end: string;
  region_id: string | null;
  totals: {
    incidents: number;
    burned_area_ha: number;
    high_severity_ha: number;
    high_severity_share: number;
    mean_confirmation_minutes: number;
  };
  series: {
    week_start: string;
    incidents: number;
    burned_area_ha: number;
    high_severity_ha: number;
    mean_confirmation_minutes: number;
  }[];
  regions: { region_id: string; name: string; incidents: number; burned_area_ha: number; high_severity_ha: number }[];
  largest_burn_scars: BurnScarSummary[];
}

export interface ObservationHistogram {
  start: string;
  end: string;
  bin_minutes: number;
  bins: { start: string; total: number; incident: number }[];
}

export type LiveHealth = "live" | "nrt" | "stale" | "offline";

export interface LiveStatus {
  mode: "live";
  source: string;
  status: LiveHealth;
  configured: boolean;
  last_fetch_at: string | null;
  latest_observation_at: string | null;
  next_refresh_at: string | null;
  refresh_interval_seconds: number;
  detection_count: number;
  incident_count: number;
  error: string | null;
}

export type AnalysisOrigin = "model_output" | "reference" | "synthetic_demo";
export type CoverageStatus = "full" | "partial" | "none";

export interface AnalysisQuery {
  datasetId: string;
  datasetVersion: string;
  bbox: BBox;
  from: string;
  to: string;
}

export interface AnalysisExample {
  bbox: BBox;
  from: string;
  to: string;
}

export interface AnalysisDataset {
  dataset_id: string;
  dataset_version: string;
  name: string;
  description: string;
  origin: AnalysisOrigin;
  processing_version: string;
  available_from: string;
  available_to: string;
  extent: BBox;
  example: AnalysisExample;
  scene_ids: string[];
  attribution: string;
  license: string;
  limitations: string[];
}

export interface AnalysisDatasetCatalog {
  schema_version: "1.0";
  items: AnalysisDataset[];
}

export interface AnalysisSourceCoverage {
  status: CoverageStatus;
  covered_area_ha: number | null;
  valid_area_ha: number | null;
}

export interface AnalysisCoverage {
  status: CoverageStatus;
  query_area_ha: number;
  covered_area_ha: number | null;
  valid_area_ha: number | null;
  active_fire: AnalysisSourceCoverage;
  burn_scars: AnalysisSourceCoverage;
  method: string;
}

export interface AnalysisSeverity {
  class_id: 1 | 2 | 3;
  label: string;
  severity: BurnSeverity;
  area_ha: number | null;
  share: number | null;
}

export interface AnalysisResult {
  schema_version: "1.0";
  result_id: string;
  request: {
    dataset_id: string;
    dataset_version: string;
    bbox: BBox;
    from: string;
    to: string;
  };
  provenance: {
    origin: AnalysisOrigin;
    processing_version: string;
    scene_ids: string[];
    observation_source: string;
    attribution: string;
    license: string;
    temporal_rule: string;
  };
  coverage: AnalysisCoverage;
  summary: {
    status: "ok" | "empty" | "no_coverage" | "no_valid_data";
    hotspot_count: number;
    burn_scar_count: number;
    zone_count: number;
    total_burned_area_ha: number | null;
    severity: AnalysisSeverity[];
  };
  hotspots: FeatureCollection<Record<string, unknown>>;
  burn_zones: FeatureCollection<Record<string, unknown>>;
  warnings: { code: string; message: string }[];
  calculation: {
    area_method: string;
    area_crs: string;
    clipping_rule: string;
    deduplication_rule: string;
    precision: string;
  };
  generated_at: string;
}
