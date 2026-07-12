import { describe, expect, it } from "vitest";

import { allColumnsAnswered, escalationLine, previewFor, toResolvePayload } from "./dateFormat";
import type { DateFormatColumn } from "../lib/types";

describe("previewFor", () => {
  it("renders a day-first preview for an ambiguous value", () => {
    expect(previewFor("03/04/2025", "day_first")).toBe("3 April 2025");
  });

  it("renders a month-first preview for the SAME ambiguous value", () => {
    expect(previewFor("03/04/2025", "month_first")).toBe("March 4, 2025");
  });

  it("returns null under an order that makes the value impossible (13 can never be a month)", () => {
    // "13/01/2025" is only sensible as day_first (13th of January); reading
    // it month_first would require a 13th month, which does not exist.
    expect(previewFor("13/01/2025", "month_first")).toBeNull();
  });

  it("returns null for a value that isn't shaped like a date at all -- never guess a garbage preview", () => {
    expect(previewFor("not-a-date", "day_first")).toBeNull();
  });
});

describe("allColumnsAnswered", () => {
  const columns: DateFormatColumn[] = [
    {
      target_field: "assay_date",
      source_column: "Experiment Date",
      day_first_format: "%d/%m/%Y",
      month_first_format: "%m/%d/%Y",
      example_values: ["03/04/2025"],
      ambiguous_row_count: 5,
    },
    {
      target_field: "collected_on",
      source_column: "Collected",
      day_first_format: "%d/%m/%Y",
      month_first_format: "%m/%d/%Y",
      example_values: ["04/05/2025"],
      ambiguous_row_count: 2,
    },
  ];

  it("is false until every ambiguous column has an order", () => {
    expect(allColumnsAnswered(columns, {})).toBe(false);
    expect(allColumnsAnswered(columns, { assay_date: "day_first" })).toBe(false);
  });

  it("is true once every column has an order -- the submit button's disabled state mirrors this", () => {
    expect(
      allColumnsAnswered(columns, { assay_date: "day_first", collected_on: "month_first" })
    ).toBe(true);
  });
});

describe("toResolvePayload", () => {
  it("emits exactly {upload_token, choices: [{target_field, order}]} -- no format-string key at all", () => {
    const payload = toResolvePayload("token-1", { assay_date: "day_first" });

    expect(payload).toEqual({
      upload_token: "token-1",
      choices: [{ target_field: "assay_date", order: "day_first" }],
    });
    // Pin the exact key shape (T-10-31): a client sending a fabricated
    // strptime format must be structurally impossible, not just untested.
    expect(Object.keys(payload)).toEqual(["upload_token", "choices"]);
    expect(Object.keys(payload.choices[0])).toEqual(["target_field", "order"]);
  });

  it("bundles every answered column into one choices array", () => {
    const payload = toResolvePayload("token-2", {
      assay_date: "day_first",
      collected_on: "month_first",
    });

    expect(payload.choices).toEqual([
      { target_field: "assay_date", order: "day_first" },
      { target_field: "collected_on", order: "month_first" },
    ]);
  });
});

describe("escalationLine", () => {
  it("omits the Claude clause entirely when claude is 0 -- the omission is the whole point of the line", () => {
    expect(escalationLine({ python: 6, claude: 0, total: 6 })).toBe(
      "6 of 6 field(s) matched from the Schema's crosswalk — 0 Claude calls."
    );
  });

  it("names the Claude count when it is non-zero", () => {
    expect(escalationLine({ python: 4, claude: 2, total: 6 })).toBe(
      "4 of 6 field(s) matched from the Schema's crosswalk. 2 required Claude."
    );
  });
});
