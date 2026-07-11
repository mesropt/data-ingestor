import { useEffect, useReducer, useRef, useState } from "react";
import { Download } from "lucide-react";

import { RegistryTable } from "@/components/RegistryTable";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, getMasterMap, listSchemas, masterMapDownloadUrl } from "@/lib/api";
import type { MasterMapEnvelope } from "@/lib/types";
import { groupFieldRows, isSchemaEmpty } from "@/state/registry";
import { initialSchemaState, schemaReducer } from "@/state/schema";

type MapStatus =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "loaded"; envelope: MasterMapEnvelope };

/**
 * The Mapping Registry screen (REG-01, REG-02, D-09-01/02/03/05) -- a
 * read-only tab that renders the whole crosswalk for a chosen Schema: a Schema
 * selector (from `GET /api/schemas`) drives a `GET /api/schemas/{name}/
 * master-map` fetch, whose canonical fields + aliases render through the
 * escape-by-default `RegistryTable`.
 *
 * Viewing is open (D-09-05) -- no sign-in wall. Every failure path resolves to
 * a visible, actionable state, never a blank pane: no schemas -> a first-run
 * hint; an empty Schema -> a Review/Import hint; a fetch failure -> a
 * consequence-first message with a Try-again re-fetch (the T-09-02 mitigation).
 */
export function Registry() {
  const [schemaState, schemaDispatch] = useReducer(schemaReducer, initialSchemaState);
  const [status, setStatus] = useState<MapStatus>({ kind: "idle" });
  // Guards against a schema-switch race: selecting A then quickly B can let
  // A's slower response land after B's, clobbering the crosswalk currently
  // shown. Tracks the most recently REQUESTED name (not the reducer's
  // `selected`, which lags a dispatch) so a stale response is a no-op --
  // latest selection always wins.
  const latestRequestRef = useRef<string | null>(null);

  useEffect(() => {
    listSchemas()
      .then((schemas) => schemaDispatch({ type: "LOADED", schemas }))
      .catch(() => {
        // A schema-list failure just leaves the selector empty; the first-run
        // hint below covers it. It never blocks the tab or other screens.
      });
  }, []);

  function loadMasterMap(name: string) {
    latestRequestRef.current = name;
    setStatus({ kind: "loading" });
    getMasterMap(name)
      .then((envelope) => {
        if (latestRequestRef.current !== name) return;
        setStatus({ kind: "loaded", envelope });
      })
      .catch((err) => {
        if (latestRequestRef.current !== name) return;
        setStatus({ kind: "error" });
        if (!(err instanceof ApiError)) {
          // Non-HTTP failures (offline, parse) still resolve to the same
          // retryable error state; nothing is thrown past this boundary.
        }
      });
  }

  function handleSelect(name: string) {
    schemaDispatch({ type: "SELECT", name });
    loadMasterMap(name);
  }

  const hasSchemas = schemaState.schemas.length > 0;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 py-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-display">Mapping Registry</h1>
        <p className="text-body text-muted-foreground">
          The governed master for a Schema and every vendor alias mapped into it — with its lineage.
        </p>
      </header>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="registry-schema-select">Schema</Label>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={schemaState.selected ?? undefined}
            onValueChange={(value) => handleSelect(String(value))}
            disabled={!hasSchemas}
          >
            <SelectTrigger id="registry-schema-select" className="w-64">
              <SelectValue placeholder={hasSchemas ? "Choose a Schema…" : "No schemas yet"} />
            </SelectTrigger>
            <SelectContent>
              {schemaState.schemas.map((schema) => (
                <SelectItem key={schema.id} value={schema.name}>
                  {schema.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {schemaState.selected && (
            <a
              href={masterMapDownloadUrl(schemaState.selected)}
              download
              className={buttonVariants({ variant: "outline" })}
            >
              <Download className="size-4" />
              Download master map
            </a>
          )}
        </div>
      </div>

      <RegistryBody hasSchemas={hasSchemas} status={status} onRetry={() => schemaState.selected && loadMasterMap(schemaState.selected)} />
    </div>
  );
}

interface RegistryBodyProps {
  hasSchemas: boolean;
  status: MapStatus;
  onRetry: () => void;
}

/** The main region below the selector -- resolves every state (no schemas,
 * nothing selected, loading, error, empty Schema, populated crosswalk) to a
 * visible, calm surface. */
function RegistryBody({ hasSchemas, status, onRetry }: RegistryBodyProps) {
  if (!hasSchemas && status.kind === "idle") {
    return (
      <EmptyCard
        title="No schemas yet"
        hint="Promote a confirmed field set to a Schema in Review, or import a master map, then it will appear here to browse its crosswalk."
      />
    );
  }

  if (status.kind === "idle") {
    return (
      <EmptyCard
        title="Choose a Schema"
        hint="Pick a Schema above to see its canonical fields and every vendor alias mapped into it."
      />
    );
  }

  if (status.kind === "loading") {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (status.kind === "error") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Couldn't load this Schema's crosswalk.</CardTitle>
          <CardDescription>
            The registry couldn't reach the server for this Schema's master map. Nothing else on this page is affected.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (isSchemaEmpty(status.envelope)) {
    return (
      <EmptyCard
        title="Nothing mapped into this Schema yet"
        hint="Confirm a mapping against this Schema in Review, or import a master map, to start accruing vendor aliases here."
      />
    );
  }

  return <RegistryTable rows={groupFieldRows(status.envelope)} />;
}

/** A calm empty/first-run card carrying a one-line consequence-free hint. */
function EmptyCard({ title, hint }: { title: string; hint: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{hint}</CardDescription>
      </CardHeader>
    </Card>
  );
}
