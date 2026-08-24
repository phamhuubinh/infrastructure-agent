import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { BrainCircuit, CheckCircle2, KeyRound, Loader2, PlugZap, Save, Trash2 } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiJson, getStoredApiKey, setStoredApiKey } from "@/lib/api";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Cài đặt — Orion" },
      { name: "description", content: "Configure Orion and model connections." },
    ],
  }),
  component: SettingsPage,
});

type ModelConnection = {
  name: string;
  provider: string;
  base_url: string;
  model: string;
  api_key_configured: boolean;
  active: boolean;
};

type ModelsResponse = {
  active_server: string;
  models: ModelConnection[];
};

export function SettingsPage() {
  const [apiKey, setApiKey] = useState(() => getStoredApiKey());
  const [apiKeySaved, setApiKeySaved] = useState(false);
  const [models, setModels] = useState<ModelConnection[]>([]);
  const [name, setName] = useState("primary");
  const [provider, setProvider] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [modelApiKey, setModelApiKey] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadModels = useCallback(async () => {
    try {
      const response = await apiJson<ModelsResponse>("/api/models");
      setModels(response.models);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể tải model.");
    }
  }, []);

  useEffect(() => {
    void loadModels();
  }, [loadModels]);

  async function perform(label: string, action: () => Promise<unknown>, success: string) {
    setBusy(label);
    setNotice("");
    setError("");
    try {
      await action();
      setNotice(success);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Thao tác thất bại.");
    } finally {
      await loadModels();
      setBusy("");
    }
  }

  function saveConnection() {
    return perform(
      "save",
      async () => {
        await apiJson("/api/models", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            provider,
            base_url: baseUrl,
            model,
            api_key: modelApiKey || undefined,
            activate: true,
          }),
        });
      },
      "Đã lưu, chọn và kiểm tra kết nối model thành công.",
    );
  }

  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader title="Cài đặt" subtitle="Cấu hình model cho Chat và phân tích RAG." />
      <div className="flex-1 overflow-y-auto p-5">
        <div className="mx-auto max-w-3xl space-y-5">
          {(error || notice) && (
            <div
              className={`rounded-lg border px-3 py-2 text-sm ${
                error
                  ? "border-destructive/30 bg-destructive/10 text-destructive"
                  : "border-success/30 bg-success/10 text-success"
              }`}
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
                <p className="text-sm text-muted-foreground mt-1">
                  Model do người dùng tự cài và vận hành. Orion chỉ lưu kết nối và kiểm tra endpoint
                  trước khi dùng cho Chat hoặc phân tích RAG.
                </p>
              </div>
            </div>

            <div className="space-y-2">
              {models.length === 0 ? (
                <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                  Chưa cấu hình model.
                </div>
              ) : (
                models.map((item) => (
                  <div
                    key={item.name}
                    className="flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{item.name}</span>
                        {item.active && <Badge>Đang dùng</Badge>}
                      </div>
                      <div className="mt-1 truncate text-xs text-muted-foreground">
                        {item.provider} · {item.model} · {item.base_url}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={Boolean(busy)}
                        onClick={() =>
                          void perform(
                            `test-${item.name}`,
                            () =>
                              apiJson(`/api/models/${encodeURIComponent(item.name)}/test`, {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                  timeout: item.provider === "ollama" ? 300 : 30,
                                }),
                              }),
                            `Kết nối ${item.name} hoạt động bình thường.`,
                          )
                        }
                      >
                        {busy === `test-${item.name}` ? (
                          <Loader2 className="h-4 w-4 animate-spin text-titanium" />
                        ) : (
                          <PlugZap className="h-4 w-4" />
                        )}
                        Kiểm tra
                      </Button>
                      {!item.active && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={Boolean(busy)}
                          onClick={() =>
                            void perform(
                              `activate-${item.name}`,
                              () =>
                                apiJson(`/api/models/${encodeURIComponent(item.name)}/activate`, {
                                  method: "POST",
                                }),
                              `Đã chọn ${item.name}.`,
                            )
                          }
                        >
                          <CheckCircle2 className="h-4 w-4" /> Chọn
                        </Button>
                      )}
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Xóa ${item.name}`}
                        disabled={Boolean(busy)}
                        onClick={() => {
                          if (!window.confirm(`Xóa cấu hình model "${item.name}"?`)) return;
                          void perform(
                            `delete-${item.name}`,
                            () =>
                              apiJson(`/api/models/${encodeURIComponent(item.name)}`, {
                                method: "DELETE",
                              }),
                            `Đã xóa ${item.name}.`,
                          );
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Tên kết nối"
              />
              <select
                value={provider}
                onChange={(event) => setProvider(event.target.value)}
                className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                aria-label="Model provider"
              >
                <option value="openai">OpenAI-compatible</option>
                <option value="ollama">Ollama</option>
                <option value="vllm">vLLM</option>
              </select>
              <Input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="Base URL, ví dụ http://localhost:11434 hoặc .../v1"
              />
              <Input
                value={model}
                onChange={(event) => setModel(event.target.value)}
                placeholder="Model name"
              />
              <Input
                className="sm:col-span-2"
                type="password"
                value={modelApiKey}
                onChange={(event) => setModelApiKey(event.target.value)}
                placeholder="API key (để trống nếu không cần)"
              />
            </div>
            <div className="flex justify-end">
              <Button
                disabled={Boolean(busy) || !name.trim() || !baseUrl.trim() || !model.trim()}
                onClick={() => void saveConnection()}
              >
                {busy === "save" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-titanium" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                Lưu & kiểm tra
              </Button>
            </div>
          </Card>

          <Card className="p-5 space-y-4">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-surface-3 p-2 text-foreground">
                <KeyRound className="h-5 w-5" />
              </div>
              <div>
                <h2 className="font-medium">API key Orion</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Chỉ dùng khi truy cập trực tiếp backend có bật ORION_API_KEY.
                </p>
              </div>
            </div>
            <Input
              type="password"
              value={apiKey}
              onChange={(event) => {
                setApiKey(event.target.value);
                setApiKeySaved(false);
              }}
              placeholder="Để trống nếu API auth đang tắt"
              aria-label="Orion API key"
            />
            <div className="flex items-center justify-end gap-3">
              {apiKeySaved && <span className="text-xs text-success">Đã lưu</span>}
              <Button
                onClick={() => {
                  setStoredApiKey(apiKey);
                  setApiKeySaved(true);
                }}
              >
                <Save className="h-4 w-4" /> Lưu
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
