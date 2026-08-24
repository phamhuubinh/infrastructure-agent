import { createFileRoute } from "@tanstack/react-router";
import { BookOpen } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/card";

export const Route = createFileRoute("/knowledge")({
  head: () => ({
    meta: [{ title: "Kiến thức — Orion" }],
  }),
  component: KnowledgePage,
});

export function KnowledgePage() {
  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader title="Kiến thức" subtitle="Tính năng này chưa có trong runtime M1." />
      <div className="flex-1 overflow-y-auto p-5">
        <div className="mx-auto max-w-3xl">
          <Card className="p-5">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-surface-3 p-2 text-foreground">
                <BookOpen className="h-5 w-5" />
              </div>
              <div>
                <h2 className="font-medium">Chưa khả dụng</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Orion M1 hiện chỉ hỗ trợ Chat và calculator. Tài liệu, RAG và Project sẽ được
                  triển khai ở một mốc sau; trang này không gọi các API chưa tồn tại.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
