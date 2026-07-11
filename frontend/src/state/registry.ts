import type { AliasPayload, MasterMapEnvelope } from "../lib/types";

export interface FieldMetadata {
  type: string | null;
  unit: string | null;
  allowedValues: string[] | null;
  min: number | null;
  max: number | null;
}

export interface FieldRow {
  name: string;
  description: string | null;
  required: boolean;
  metadata: FieldMetadata;
  aliases: AliasPayload[];
  hasAliases: boolean;
}

export interface Provenance {
  kind: string;
  label: string;
  actor: string;
  when: string;
}

// RED stub — intentionally unimplemented until GREEN.
export function groupFieldRows(_envelope: MasterMapEnvelope): FieldRow[] {
  return [];
}

export function formatProvenance(_alias: AliasPayload): Provenance {
  return { kind: "", label: "", actor: "", when: "" };
}

export function formatWhen(_createdAt: string): string {
  return "";
}

export function isSchemaEmpty(_envelope: MasterMapEnvelope): boolean {
  return false;
}
