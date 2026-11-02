import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { BrainCircuit, Loader2, Pencil, Plus, Save, Trash2 } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiErrorMessage, apiFetch, apiJson } from "@/lib/api";
import { ServerConnections } from "@/components/ServerConnections";
import { RuntimeResources } from "@/components/RuntimeResources";
import { isNativeHost, serverRequest } from "@/lib/server-profiles";
import type { Schemas } from "@/lib/sdk/generated";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Cài đặt — Orion" },
      { name: "description", content: "Configure Orion model connection." },
    ],
  }),
  component: SettingsPage,
});

type ModelConnection = Schemas["ModelConfigView"];
type Provider = Schemas["ModelProfile"]["provider_id"];

export function SettingsPage() {
  const [models, setModels] = useState<ModelConnection[]>([]);
  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [provider, setProvider] = useState<Provider>("openai_compatible");
  const [protocol, setProtocol] = useState<Schemas["ModelProfile"]["protocol"]>("chat_completions");
  const [credentialRef, setCredentialRef] = useState("");
  const [tools, setTools] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [reasoningMode, setReasoningMode] = useState<ModelConnection["reasoning_mode"]>("auto");
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

  useEffect(() => {
    void loadModels();
  }, [loadModels]);

  function resetModelForm() {
    setBaseUrl("");
    setModelId("");
    setApiKey("");
    setProvider("openai_compatible");
    setProtocol("chat_completions");
    setCredentialRef("");
    setTools(false);
    setStreaming(false);
    setReasoningMode("auto");
    setEditingModel(null);
    setAddingModel(false);
  }

  function editModel(model: ModelConnection) {
    setBaseUrl(model.base_url);
    setModelId(model.model_id);
    setApiKey("");
    setProvider(model.provider_type as Provider);
    setProtocol(model.profile?.protocol ?? "chat_completions");
    setCredentialRef(model.profile?.credential_ref ?? "");
    setTools(model.profile?.capabilities.tools ?? false);
    setStreaming(model.profile?.capabilities.streaming ?? false);
    setReasoningMode(model.reasoning_mode);
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
      const typedProfile =
        provider !== "openai_compatible" ||
        isNativeHost() ||
        Boolean(editingModel?.profile) ||
        Boolean(credentialRef) ||
        tools ||
        streaming;
      const profile: Schemas["ModelProfile"] | undefined = typedProfile
        ? {
            ...editingModel?.profile,
            profile_id: editingModel?.profile?.profile_id ?? crypto.randomUUID(),
            provider_id: provider,
            protocol,
            endpoint: baseUrl,
            model_id: modelId,
            credential_ref: credentialRef || null,
            capabilities: {
              ...editingModel?.profile?.capabilities,
              text: true,
              tools,
              tool_result_continuation: tools,
              streaming,
            },
          }
        : undefined;
      const body: Schemas["ModelConfigInput"] = {
        provider_type: provider,
        base_url: baseUrl,
        model_id: modelId,
        api_key: typedProfile ? undefined : apiKey || undefined,
        reasoning_mode: reasoningMode,
        profile,
      };
      if (editingModel)
        await serverRequest("update_model_api_models__model_config_id__put", {
          path: { model_config_id: editingModel.model_config_id },
          body,
        });
      else await serverRequest("configure_model_api_models_post", { body });
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
          <ServerConnections />
          <RuntimeResources />
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
                  DeepSeek, Claude và OpenAI dùng adapter riêng. Model ID và credential reference do
                  chủ server cấu hình.
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
                        {item.provider_type} · {item.base_url} · {item.reasoning_mode}
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
                    <label>
                      Provider
                      <select
                        className="block w-full rounded border bg-background p-2"
                        value={provider}
                        onChange={(event) => {
                          const value = event.target.value as Provider;
                          setProvider(value);
                          setProtocol(
                            value === "claude"
                              ? "anthropic_messages"
                              : value === "openai"
                                ? "openai_responses"
                                : "chat_completions",
                          );
                          setApiKey("");
                        }}
                      >
                        <option value="deepseek">DeepSeek</option>
                        <option value="claude">Claude</option>
                        <option value="openai">OpenAI</option>
                        <option value="openai_compatible">OpenAI-compatible</option>
                      </select>
                    </label>
                    {provider === "openai" && (
                      <label>
                        Protocol
                        <select
                          className="block w-full rounded border bg-background p-2"
                          value={protocol}
                          onChange={(event) => setProtocol(event.target.value as typeof protocol)}
                        >
                          <option value="openai_responses">Responses</option>
                          <option value="chat_completions">Chat Completions</option>
                        </select>
                      </label>
                    )}
                    <label>
                      Credential reference trên server
                      <Input
                        value={credentialRef}
                        maxLength={128}
                        onChange={(event) => setCredentialRef(event.target.value)}
                        placeholder="env:ORION_PROVIDER_KEY"
                      />
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={tools}
                        onChange={(event) => setTools(event.target.checked)}
                      />
                      Model hỗ trợ tools và continuation
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={streaming}
                        onChange={(event) => setStreaming(event.target.checked)}
                      />
                      Model hỗ trợ streaming
                    </label>
                    <Input
                      value={baseUrl}
                      onChange={(event) => setBaseUrl(event.target.value)}
                      placeholder="Base URL, ví dụ http://localhost:11434/v1"
                    />
                    <label className="grid gap-1 text-sm text-muted-foreground">
                      Reasoning mode
                      <select
                        value={reasoningMode}
                        onChange={(event) =>
                          setReasoningMode(event.target.value as ModelConnection["reasoning_mode"])
                        }
                        className="h-9 rounded-md border border-input bg-transparent px-3 text-sm text-foreground"
                      >
                        <option value="auto">Auto (provider default)</option>
                        <option value="enabled">Enabled</option>
                        <option value="disabled">Disabled</option>
                      </select>
                    </label>
                    <Input
                      value={modelId}
                      onChange={(event) => setModelId(event.target.value)}
                      placeholder="Model name"
                    />
                    {provider === "openai_compatible" &&
                      !isNativeHost() &&
                      !credentialRef &&
                      !tools &&
                      !streaming &&
                      !editingModel?.profile && (
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
                      )}
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
        </div>
      </div>
    </div>
  );
}
