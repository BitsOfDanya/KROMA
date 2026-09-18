import type { AnalysisDataset, AnalysisQuery, BBox } from "@/lib/api/types";

export interface AnalysisDraft {
  datasetId: string;
  datasetVersion: string;
  west: string;
  south: string;
  east: string;
  north: string;
  from: string;
  to: string;
}

export interface DraftValidation {
  query: AnalysisQuery | null;
  errors: Partial<Record<keyof AnalysisDraft | "bbox", string>>;
}

export const EMPTY_DRAFT: AnalysisDraft = {
  datasetId: "",
  datasetVersion: "",
  west: "",
  south: "",
  east: "",
  north: "",
  from: "",
  to: "",
};

const coordinate = (value: string) => {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export function queryToDraft(query: AnalysisQuery): AnalysisDraft {
  return {
    datasetId: query.datasetId,
    datasetVersion: query.datasetVersion,
    west: String(query.bbox[0]),
    south: String(query.bbox[1]),
    east: String(query.bbox[2]),
    north: String(query.bbox[3]),
    from: query.from,
    to: query.to,
  };
}

export function exampleDraft(dataset: AnalysisDataset): AnalysisDraft {
  return queryToDraft({
    datasetId: dataset.dataset_id,
    datasetVersion: dataset.dataset_version,
    bbox: dataset.example.bbox,
    from: dataset.example.from,
    to: dataset.example.to,
  });
}

export function validateDraft(draft: AnalysisDraft): DraftValidation {
  const errors: DraftValidation["errors"] = {};
  if (!draft.datasetId) errors.datasetId = "Выберите подготовленный набор";
  if (!draft.datasetVersion) errors.datasetVersion = "Версия набора обязательна";
  const bboxValues = [draft.west, draft.south, draft.east, draft.north].map(coordinate);
  if (bboxValues.some((value) => value === null)) {
    errors.bbox = "Введите четыре конечные координаты";
  }
  const bbox = bboxValues as BBox;
  if (
    !errors.bbox &&
    !(-180 <= bbox[0] && bbox[0] < bbox[2] && bbox[2] <= 180 && -90 <= bbox[1] && bbox[1] < bbox[3] && bbox[3] <= 90)
  ) {
    errors.bbox = "Проверьте порядок запад < восток и юг < север в пределах WGS84";
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.from)) errors.from = "Укажите начальную дату";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.to)) errors.to = "Укажите конечную дату";
  if (!errors.from && !errors.to && draft.from > draft.to) {
    errors.to = "Конечная дата не может быть раньше начальной";
  }
  if (Object.keys(errors).length) return { query: null, errors };
  return {
    query: {
      datasetId: draft.datasetId,
      datasetVersion: draft.datasetVersion,
      bbox,
      from: draft.from,
      to: draft.to,
    },
    errors,
  };
}

export function queryFromSearch(search: URLSearchParams): AnalysisQuery | null {
  const datasetId = search.get("dataset") ?? "";
  const datasetVersion = search.get("version") ?? "";
  const bbox = search.get("bbox")?.split(",") ?? [];
  const from = search.get("from") ?? "";
  const to = search.get("to") ?? "";
  const result = validateDraft({
    datasetId,
    datasetVersion,
    west: bbox[0] ?? "",
    south: bbox[1] ?? "",
    east: bbox[2] ?? "",
    north: bbox[3] ?? "",
    from,
    to,
  });
  return result.query;
}

export function querySearch(query: AnalysisQuery): string {
  const params = new URLSearchParams({
    tab: "area",
    dataset: query.datasetId,
    version: query.datasetVersion,
    bbox: query.bbox.join(","),
    from: query.from,
    to: query.to,
  });
  return params.toString();
}

export function sameQuery(left: AnalysisQuery | null, right: AnalysisQuery | null): boolean {
  return Boolean(
    left &&
      right &&
      left.datasetId === right.datasetId &&
      left.datasetVersion === right.datasetVersion &&
      left.from === right.from &&
      left.to === right.to &&
      left.bbox.every((value, index) => value === right.bbox[index]),
  );
}
