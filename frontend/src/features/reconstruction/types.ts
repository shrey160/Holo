export type Span = {
  plane_id: string;
  endpoints_floor_uv_m: number[][];
  projected_span_estimated_m: number;
  observed_height_range_above_floor_m: number[];
};
export type Cell = { cell: number[] };
export type CeilingEstimate = {
  height_estimated_m: number | null;
  status: string;
  support_band_m: number[] | null;
  ceiling_plane_verified: boolean;
};
export type ApproximateObject = {
  id: string;
  label: string;
  status: string;
  footprint_floor_uv_m?: number[][];
  color?: string;
};
export type Scene = {
  inferred_room_completion?: {
    axes_in_floor_uv?: number[][];
    polygon_floor_uv_m?: number[][];
    ceiling_estimate?: CeilingEstimate;
  };
  approximate_objects?: ApproximateObject[];
  label: string;
  point_count: number;
  geometry_source?: string;
  source_voxel_points: number;
  selected_views: number;
  bounds: number[][];
  camera_path: number[][];
  floor_cells: Cell[];
  cell_m: number;
  reviewed_spans: Span[];
};
export type Plan = {
  roomwise?: RoomwiseReport;
  rough_room?: {
    ceiling_estimate?: CeilingEstimate;
    objects?: ApproximateObject[];
    status: string;
    dimensions_estimated_m: number[];
    area_estimated_m2: number;
    ceiling_reference: { value_m: number; precision: string } | null;
  };
  structure?: {
    policy: { cell_m: number };
    cells: { cell: number[]; height_range_m: number[]; voxel_points: number }[];
    suggested_spans: { plane_id: string; uv: number[][]; status: string }[];
    retained_voxel_points: number;
  };
  raster: {
    width: number;
    height: number;
    bounds_uv_m: number[][];
    scale_px_per_estimated_m: number;
    padding_px: number[];
  };
  floor_cells: Cell[];
  cell_m: number;
  reviewed_spans: Span[];
  candidate_spans: { plane_id: string; uv: number[][]; status: string }[];
  camera_path_uv_m: number[][];
};
export type RoomwiseReport = {
  status: string;
  rooms: {
    id: string;
    status: string;
    failure?: string;
    source_voxel_count: number;
    scanning_ranks: number[];
    approach_ranks: number[];
    structure?: NonNullable<Plan["structure"]>;
    rough_room:
      | (NonNullable<Plan["rough_room"]> & { polygon_floor_uv_m: number[][] })
      | null;
  }[];
  route: {
    stays: {
      room_id: string;
      scan_seconds: number[];
      path_floor_uv_m: number[][];
    }[];
    transitions: {
      from_room: string;
      to_room: string;
      seconds: number[];
      path_floor_uv_m: number[][];
    }[];
  };
};
export type Result = {
  id: string;
  label: string;
  point_count: number;
  geometry_source?: string;
  source_voxel_points: number;
  selected_views: number;
};
export async function readAsset<T>(
  url: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok)
    throw new Error(`Unable to load reconstruction (${response.status}).`);
  return response.json() as Promise<T>;
}
