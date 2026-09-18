import { describe, expect, it } from "vitest";

import { queryFromSearch, querySearch, validateDraft } from "./query";

const draft = {
  datasetId: "kroma-ci-demo",
  datasetVersion: "1.0.0",
  west: "99.03",
  south: "58.03",
  east: "99.13",
  north: "58.13",
  from: "2024-08-10",
  to: "2024-08-20",
};

describe("analysis query", () => {
  it("round-trips through URL without coordinate rounding", () => {
    const query = validateDraft({ ...draft, west: "99.030000123" }).query!;
    const restored = queryFromSearch(new URLSearchParams(querySearch(query)));
    expect(restored).toEqual(query);
    expect(restored?.bbox[0]).toBe(99.030000123);
  });

  it("rejects inverted boxes and dates", () => {
    const result = validateDraft({ ...draft, east: "98", to: "2024-08-01" });
    expect(result.query).toBeNull();
    expect(result.errors.bbox).toBeTruthy();
    expect(result.errors.to).toBeTruthy();
  });

  it("rejects non-finite coordinates", () => {
    expect(validateDraft({ ...draft, west: "NaN" }).errors.bbox).toBeTruthy();
    expect(validateDraft({ ...draft, west: "Infinity" }).errors.bbox).toBeTruthy();
  });
});
