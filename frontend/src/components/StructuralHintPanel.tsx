import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { StructuralHintIn, StructuralQuestionResponse } from "@/lib/types";

interface StructuralHintPanelProps {
  question: StructuralQuestionResponse;
  headersOnly: boolean;
  submitting: boolean;
  onResolve: (hint: StructuralHintIn) => void;
}

/**
 * Placeholder for Task 3's full inline structural-hint form (D-04, P2/CR-01)
 * -- this minimal version exists only so the Upload screen (Task 2) has a
 * real component to render on `kind:"structural_question"` and the app
 * builds/routes correctly; Task 3 replaces this body with the full
 * headers-only-safe evidence preview + per-dimension answer controls +
 * "Use This and Re-parse" resolve flow per 04-UI-SPEC.md.
 */
export function StructuralHintPanel({ question }: StructuralHintPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-heading">Help us find the table</CardTitle>
        <p className="text-body text-muted-foreground">{question.reason}</p>
      </CardHeader>
      <CardContent>
        <p className="text-body text-muted-foreground">
          Answer controls are built in Task 3 of this plan.
        </p>
      </CardContent>
    </Card>
  );
}
