import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { BrainCircuit, Globe2, Loader2, Save } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiJson } from "@/lib/api";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Cài đặt — Orion" },
      { name: "description", content: "Configure Orion model connection." },
    ],
  }),
  component: SettingsPage,
});

type ModelConnection = {
  model_config_id: string;
  provider_type: string;
  base_url: string;
  model_id: string;
};

type InternetIntegration = {
  status: "configured" | "unavailable";
  provider: string | null;
  endpoint: string | null;
  message: string | null;
};

export function SettingsPage() {
  const [models, setModels] = useState<ModelConnection[]>([]);
  const [internet, setInternet] = useState<InternetIntegration | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadModels = useCallback(async () => {
    try {
      setModels(await apiJson<ModelConnection[]>("/api/models"));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể tải model.");
    }
  }, []);

  const loadInternet = useCallback(async () => {
    try {
      setInternet(await apiJson<InternetIntegration>("/api/integrations/internet"));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể tải Internet.");
    }
  }, []);

  useEffect(() => {
    void loadModels();
    void loadInternet();
  }, [loadInternet, loadModels]);

  async function saveConnection() {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      await apiJson<ModelConnection>("/api/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_type: "openai_compatible",
          base_url: baseUrl,
          model_id: modelId,
          api_key: apiKey || undefined,
        }),
      });
      // Credentials remain request-only: never put them in browser persistence or rendered state.
      setApiKey("");
      setNotice("Đã lưu cấu hình model.");
      await loadModels();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể lưu model.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader title="Cài đặt" subtitle="Cấu hình model đang dùng cho Chat." />
      <div className="flex-1 overflow-y-auto p-5">
        <div className="mx-auto max-w-3xl space-y-5">
          {(error || notice) && (
            <div
              className={
                "rounded-lg border px-3 py-2 text-sm " +
                (error
                  ? "border-destructive/30 bg-destructive/10 text-destructive"
                  : "border-success/30 bg-success/10 text-success")
              }
            >
              {error || notice}
            </div>
          )}
          <Card className="p-5 space-y-4">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-surface-3 p-2 text-foreground">
                <BrainCircuit className="h-5 w-5" />
              </div>
              <div>
                <h2 className="font-medium">Kết nối model</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Orion dùng một cấu hình OpenAI-compatible đang hoạt động cho Chat.
                </p>
              </div>
            </div>

            {models.length === 0 ? (
              <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                Chưa cấu hình model.
              </div>
            ) : (
              models.map((item) => (
                <div
                  key={item.model_config_id}
                  className="flex items-center gap-3 rounded-lg border p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{item.model_id}</span>
                      <Badge>Đang dùng</Badge>
                    </div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">
                      {item.provider_type} · {item.base_url}
                    </div>
                  </div>
                </div>
              ))
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="Base URL, ví dụ http://localhost:11434/v1"
              />
              <Input
                value={modelId}
                onChange={(event) => setModelId(event.target.value)}
                placeholder="Model name"
              />
              <Input
                className="sm:col-span-2"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="API key (để trống nếu không cần)"
                autoComplete="off"
              />
            </div>
            <div className="flex justify-end">
              <Button
                disabled={busy || !baseUrl.trim() || !modelId.trim()}
                onClick={() => void saveConnection()}
              >
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin text-titanium" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                Lưu model
              </Button>
            </div>
          </Card>
          <Card className="p-5 space-y-3">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-surface-3 p-2 text-foreground">
                <Globe2 className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h2 className="font-medium">Internet</h2>
                  {internet && (
                    <Badge>{internet.status === "configured" ? "Sẵn sàng" : "Chưa cấu hình"}</Badge>
                  )}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {internet?.status === "configured"
                    ? `Tìm kiếm qua ${internet.provider ?? "integration"}: ${internet.endpoint}`
                    : (internet?.message ?? "Đang tải trạng thái tích hợp Internet.")}
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
