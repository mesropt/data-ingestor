import { describe, expect, it } from "vitest";

import { buildResolvePayload, initialReconcileChoices, setChoice } from "./reconcile";
import type { ReconcileConflict } from "../lib/types";

const conflicts: ReconcileConflict[] = [
  {
    vendor: "novascreen",
    source_column: "Cmpd",
    master_field: "compound_id",
    map_file_field: "batch_id",
  },
  {
    vendor: "novascreen",
    source_column: "Result",
    master_field: "value",
    map_file_field: "ic50",
  },
];

describe("initialReconcileChoices", () => {
  it("defaults every conflict to keep_master (the no-op-against-master safe default)", () => {
    expect(initialReconcileChoices(conflicts)).toEqual([
      { vendor: "novascreen", source_column: "Cmpd", decision: "keep_master" },
      { vendor: "novascreen", source_column: "Result", decision: "keep_master" },
    ]);
  });

  it("returns an empty list for no conflicts", () => {
    expect(initialReconcileChoices([])).toEqual([]);
  });
});

describe("setChoice", () => {
  it("updates only the matching (vendor, source_column) conflict", () => {
    const state = initialReconcileChoices(conflicts);

    const next = setChoice(state, "Result", "novascreen", "take_map_file");

    expect(next).toEqual([
      { vendor: "novascreen", source_column: "Cmpd", decision: "keep_master" },
      { vendor: "novascreen", source_column: "Result", decision: "take_map_file" },
    ]);
  });

  it("does not mutate the previous state array", () => {
    const state = initialReconcileChoices(conflicts);

    setChoice(state, "Cmpd", "novascreen", "take_map_file");

    expect(state[0].decision).toBe("keep_master");
  });

  it("is a no-op when no conflict matches", () => {
    const state = initialReconcileChoices(conflicts);

    expect(setChoice(state, "Unknown", "novascreen", "take_map_file")).toEqual(state);
  });
});

describe("buildResolvePayload", () => {
  it("emits exactly {upload_token, choices:[{vendor, source_column, decision}]} with one entry per conflict and no extras", () => {
    const choices = setChoice(
      initialReconcileChoices(conflicts),
      "Result",
      "novascreen",
      "take_map_file"
    );

    expect(buildResolvePayload("tok-9", choices)).toEqual({
      upload_token: "tok-9",
      choices: [
        { vendor: "novascreen", source_column: "Cmpd", decision: "keep_master" },
        { vendor: "novascreen", source_column: "Result", decision: "take_map_file" },
      ],
    });
  });

  it("carries an empty choices list when there were no conflicts", () => {
    expect(buildResolvePayload("tok-0", initialReconcileChoices([]))).toEqual({
      upload_token: "tok-0",
      choices: [],
    });
  });
});
