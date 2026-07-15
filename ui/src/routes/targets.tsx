import { createFileRoute } from "@tanstack/react-router";
import { Target, Construction } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";

export const Route = createFileRoute("/targets")({
  head: () => ({
    meta: [
      { title: "Mục tiêu — Orion" },
      { name: "description", content: "Managed targets." },
    ],
  }),
  component: TargetsPage,
});

function TargetsPage() {
  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader title="Targets" subtitle="Managed execution targets." />
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <Construction className="h-12 w-12 text-muted-foreground/40 mx-auto mb-3" />
          <h2 className="text-lg font-medium">Not implemented yet</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Target management will be available soon.
          </p>
        </div>
      </div>
    </div>
  );
}
