import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  BrainCircuit,
  Globe2,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Server,
  Trash2,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiErrorMessage, apiFetch, apiJson } from "@/lib/api";

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
  is_active: boolean;
};

type InternetIntegration = {
  status: "unconfigured" | "healthy" | "unhealthy";
  provider: string | null;
  endpoint: string | null;
  message: string | null;
};

type InfrastructureIntegration = {
  status: "unconfigured" | "healthy" | "unhealthy";
  message: string | null;
};

export function SettingsPage() {
  const [models, setModels] = useState<ModelConnection[]>([]);
  const [internet, setInternet] = useState<InternetIntegration | null>(null);
  const [infrastructure, setInfrastructure] = useState<Record<string, InfrastructureIntegration>>(
    {},
  );
  const [integrationErrors, setIntegrationErrors] = useState<Record<string, string>>({});
  const [refreshingIntegrations, setRefreshingIntegrations] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [editingModel, setEditingModel] = useState<ModelConnection | null>(null);
  const [addingModel, setAddingModel] = useState(false);
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

  const loadIntegrations = useCallback(async () => {
    setRefreshingIntegrations(true);
    const targets = ["internet", "linux", "grafana", "zabbix"] as const;
    const results = await Promise.allSettled(
      targets.map(async (family) => {
        const path =
          family === "internet" ? "/api/integrations/internet" : `/api/integrations/${family}`;
        return [
          family,
          await apiJson<InternetIntegration | InfrastructureIntegration>(path),
        ] as const;
      }),
    );
    const nextErrors: Record<string, string> = {};
    results.forEach((result, index) => {
      const family = targets[index];
      if (result.status === "rejected") {
        nextErrors[family] = "Không thể tải trạng thái tích hợp.";
        return;
      }
      const [, status] = result.value;
      if (family === "internet") setInternet(status as InternetIntegration);
      else setInfrastructure((current) => ({ ...current, [family]: status }));
    });
    setIntegrationErrors(nextErrors);
    setRefreshingIntegrations(false);
  }, []);

  useEffect(() => {
    void loadModels();
    void loadIntegrations();
  }, [loadIntegrations, loadModels]);

  function resetModelForm() {
    setBaseUrl("");
    setModelId("");
    setApiKey("");
    setEditingModel(null);
    setAddingModel(false);
  }

  function editModel(model: ModelConnection) {
    setBaseUrl(model.base_url);
    setModelId(model.model_id);
    setApiKey("");
    setEditingModel(model);
    setAddingModel(false);
    setNotice("");
    setError("");
  }

  function addModel() {
    resetModelForm();
    setAddingModel(true);
    setNotice("");
    setError("");
  }

  async function saveConnection() {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const path = editingModel
        ? `/api/models/${encodeURIComponent(editingModel.model_config_id)}`
        : "/api/models";
      await apiJson<ModelConnection>(path, {
        method: editingModel ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_type: "openai_compatible",
          base_url: baseUrl,
          model_id: modelId,
          api_key: apiKey || undefined,
        }),
      });
      // Credentials remain request-only: never put them in browser persistence or rendered state.
      const wasEditing = Boolean(editingModel);
      resetModelForm();
      setNotice(wasEditing ? "Đã cập nhật cấu hình model." : "Đã lưu cấu hình model.");
      await loadModels();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể lưu model.");
    } finally {
      setBusy(false);
    }
  }

  async function activateModel(modelConfigId: string) {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      await apiJson<ModelConnection>(`/api/models/${encodeURIComponent(modelConfigId)}/activate`, {
        method: "POST",
      });
      setNotice("Đã chọn model đang dùng.");
      await loadModels();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể chọn model.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteModel(modelConfigId: string) {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const response = await apiFetch(`/api/models/${encodeURIComponent(modelConfigId)}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      setNotice("Đã xóa model đã lưu.");
      await loadModels();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể xóa model.");
    } finally {
      setBusy(false);
    }
  }

  const formVisible = models.length === 0 || addingModel || editingModel !== null;

  return (
    <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
      <PageHeader
        title={models.length === 0 ? "Thiết lập Orion" : "Cài đặt"}
        subtitle={
          models.length === 0
            ? "Kết nối model đầu tiên để bắt đầu trò chuyện với Orion."
            : "Quản lý các model đã lưu. Chat và Project dùng model đang chọn."
        }
      />
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
                Đây là thiết lập Orion lần đầu. Lưu một model để quay lại Chat.
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm text-muted-foreground">Model đã lưu</div>
                  <Button size="sm" variant="outline" onClick={addModel} disabled={busy}>
                    <Plus className="h-4 w-4" />
                    Thêm model
                  </Button>
                </div>
                {models.map((item) => (
                  <div
                    key={item.model_config_id}
                    className="flex items-center gap-3 rounded-lg border p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{item.model_id}</span>
                        {item.is_active && <Badge>Đang dùng</Badge>}
                      </div>
                      <div className="mt-1 truncate text-xs text-muted-foreground">
                        {item.provider_type} · {item.base_url}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {!item.is_active && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void activateModel(item.model_config_id)}
                          disabled={busy}
                        >
                          Dùng model này
                        </Button>
                      )}
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => editModel(item)}
                        disabled={busy}
                        aria-label={`Edit ${item.model_id}`}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      {!item.is_active && (
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => void deleteModel(item.model_config_id)}
                          disabled={busy}
                          aria-label={`Delete ${item.model_id}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {formVisible && (
              <>
                <div className="border-t pt-4">
                  <div className="mb-3 text-sm font-medium">
                    {editingModel ? "Chỉnh sửa model" : "Thêm model"}
                  </div>
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
                      placeholder={
                        editingModel
                          ? "API key (để trống để giữ nguyên)"
                          : "API key (để trống nếu không cần)"
                      }
                      autoComplete="off"
                    />
                  </div>
                </div>
                <div className="mt-3 flex justify-end gap-2">
                  {(editingModel || addingModel) && (
                    <Button variant="ghost" onClick={resetModelForm} disabled={busy}>
                      Hủy
                    </Button>
                  )}
                  <Button
                    disabled={busy || !baseUrl.trim() || !modelId.trim()}
                    onClick={() => void saveConnection()}
                  >
                    {busy ? (
                      <Loader2 className="h-4 w-4 animate-spin text-titanium" />
                    ) : (
                      <Save className="h-4 w-4" />
                    )}
                    {editingModel ? "Lưu thay đổi" : "Lưu model"}
                  </Button>
                </div>
              </>
            )}
          </Card>
          <Card className="p-5 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="rounded-lg bg-surface-3 p-2 text-foreground">
                  <Server className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="font-medium">Tích hợp</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Orion tự sử dụng các công cụ khả dụng khi model cần. Các tích hợp này được cấu
                    hình trên máy chạy Orion, không bật/tắt theo từng cuộc trò chuyện.
                  </p>
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => void loadIntegrations()}
                disabled={refreshingIntegrations}
              >
                {refreshingIntegrations ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                Làm mới trạng thái
              </Button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <IntegrationCard
                label="Internet"
                icon={<Globe2 className="h-4 w-4" />}
                item={internet}
                error={integrationErrors.internet}
              />
              {(["linux", "grafana", "zabbix"] as const).map((family) => (
                <IntegrationCard
                  key={family}
                  label={family === "linux" ? "Linux" : family === "grafana" ? "Grafana" : "Zabbix"}
                  item={infrastructure[family]}
                  error={integrationErrors[family]}
                />
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function IntegrationCard({
  label,
  icon,
  item,
  error,
}: {
  label: string;
  icon?: ReactNode;
  item: InternetIntegration | InfrastructureIntegration | null | undefined;
  error?: string;
}) {
  const status = error ? "unhealthy" : item?.status;
  const labelForStatus =
    status === "healthy"
      ? "Sẵn sàng"
      : status === "unconfigured"
        ? "Chưa cấu hình"
        : status === "unhealthy"
          ? "Không khả dụng"
          : "Đang tải";
  return (
    <div className="rounded-lg border p-3 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 font-medium">
          {icon}
          {label}
        </span>
        <Badge>{labelForStatus}</Badge>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {error ??
          item?.message ??
          (status === "healthy"
            ? "Sẵn sàng để Orion sử dụng tự động khi cần."
            : "Đang tải trạng thái tích hợp.")}
      </p>
    </div>
  );
}
