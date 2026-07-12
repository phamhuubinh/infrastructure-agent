import { createFileRoute } from "@tanstack/react-router";
import { Settings, Construction } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings — Infrastructure Agent" }, { name: "description", content: "Configure your workspace." }] }),
  component: SettingsPage,
});

function SettingsPage() {
  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader title="Settings" subtitle="Configure your workspace." />
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <Construction className="h-12 w-12 text-muted-foreground/40 mx-auto mb-3" />
          <h2 className="text-lg font-medium">Not implemented yet</h2>
          <p className="text-sm text-muted-foreground mt-1">Settings will be available soon.</p>
        </div>
      </div>
    </div>
  );
}
