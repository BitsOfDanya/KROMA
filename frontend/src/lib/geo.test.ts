import { describe, expect, it } from "vitest";

import { buildQuery } from "./api/client";
import { haversineKm, parseNumber, snapBBox, unionBBox } from "./geo";

describe("geo helpers", () => {
  it("snaps bbox to a padded grid", () => {
    expect(snapBBox([92.4, 55.1, 101.7, 61.2])).toEqual([80, 40, 120, 80]);
  });

  it("unions bounding boxes", () => {
    expect(unionBBox([[1, 2, 3, 4], [0, 3, 5, 6]])).toEqual([0, 2, 5, 6]);
    expect(unionBBox([])).toBeNull();
  });

  it("measures great-circle distance", () => {
    expect(haversineKm([92.8932, 56.0153], [99.1797, 58.6036])).toBeCloseTo(474.4, 0);
  });

  it("validates numeric URL parameters", () => {
    expect(parseNumber("58.4", -90, 90)).toBe(58.4);
    expect(parseNumber("120", -90, 90)).toBeNull();
    expect(parseNumber("abc", -90, 90)).toBeNull();
  });
});

describe("buildQuery", () => {
  it("skips empty values and joins arrays", () => {
    expect(buildQuery({ status: ["confirmed", "suspected"], region: null, priority_min: 70, q: "" })).toBe(
      "?status=confirmed%2Csuspected&priority_min=70",
    );
  });
});
