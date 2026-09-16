import { describe, expect, it } from "vitest";

import { compassPoint, formatArea, formatDistance, formatRelative, pluralize } from "./format";

const normalize = (value: string) => value.replace(/\s/g, " ");

describe("formatArea", () => {
  it("uses hectares for small and medium areas", () => {
    expect(normalize(formatArea(814))).toBe("814 га");
    expect(normalize(formatArea(1860))).toBe("1 860 га");
    expect(normalize(formatArea(4.25))).toBe("4,3 га");
  });

  it("switches to square kilometres for large areas", () => {
    expect(normalize(formatArea(18_420))).toBe("184 км²");
  });
});

describe("formatDistance", () => {
  it("uses metres below one kilometre", () => {
    expect(normalize(formatDistance(0.42))).toBe("420 м");
  });

  it("keeps one decimal for kilometres", () => {
    expect(formatDistance(17.84)).toBe("17,8 км");
  });
});

describe("formatRelative", () => {
  const now = Date.parse("2026-09-16T12:00:00Z");

  it("formats past minutes and hours", () => {
    expect(formatRelative("2026-09-16T11:56:00Z", now)).toBe("4 мин назад");
    expect(formatRelative("2026-09-16T09:00:00Z", now)).toBe("3 ч назад");
  });

  it("formats future passes", () => {
    expect(formatRelative("2026-09-16T12:38:00Z", now)).toBe("через 38 мин");
    expect(formatRelative("2026-09-17T05:05:00Z", now)).toBe("через 17 ч");
  });
});

describe("pluralize and compass", () => {
  it("chooses Russian plural forms", () => {
    const forms: [string, string, string] = ["событие", "события", "событий"];
    expect(pluralize(1, forms)).toBe("1 событие");
    expect(pluralize(3, forms)).toBe("3 события");
    expect(pluralize(11, forms)).toBe("11 событий");
  });

  it("maps bearings to compass points", () => {
    expect(compassPoint(311)).toBe("СЗ");
    expect(compassPoint(131)).toBe("ЮВ");
  });
});
