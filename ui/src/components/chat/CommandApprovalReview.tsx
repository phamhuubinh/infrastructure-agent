import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  getToolAuthorizationPayload,
  resolveToolAuthorization,
  type ToolAuthorizationPayload,
} from "@/lib/api";

export function CommandApprovalReview({
  sessionId,
  requestId,
  callId,
  toolName,
  onResolved,
}: {
  sessionId: string;
  requestId: string;
  callId: string;
  toolName: string;
  onResolved: () => void;
}) {
  const [payload, setPayload] = useState<ToolAuthorizationPayload | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let disposed = false;
    setPayload(null);
    void getToolAuthorizationPayload(sessionId, requestId, callId)
      .then((value) => {
        if (disposed) return;
        if (
          value.tool_name !== toolName ||
          !/^[0-9a-f]{64}$/.test(value.payload_hash) ||
          !value.arguments ||
          typeof value.arguments !== "object" ||
          typeof value.arguments.target_ref !== "string" ||
          (toolName === "system.command.run" && typeof value.arguments.command !== "string") ||
          (toolName === "system.command.cancel" && typeof value.arguments.command_id !== "string")
        ) {
          setError("Không thể xác minh lệnh đang chờ.");
          return;
        }
        setPayload(value);
      })
      .catch(() => {
        if (!disposed) setError("Lệnh không còn chờ xác nhận hoặc không tải được.");
      });
    return () => {
      disposed = true;
    };
  }, [sessionId, requestId, callId, toolName]);

  async function decide(decision: "allow" | "deny") {
    if (busy || (decision === "allow" && !payload)) return;
    setBusy(true);
    try {
      await resolveToolAuthorization(sessionId, requestId, callId, decision, payload?.payload_hash);
      onResolved();
    } catch {
      setError("Không thể xác nhận lệnh; hãy kiểm tra trạng thái hiện tại.");
    } finally {
      setBusy(false);
    }
  }

  const args = payload?.arguments;
  return (
    <div className="mt-2 space-y-2">
      {!payload && !error && <p>Đang tải lệnh chờ xác nhận…</p>}
      {args && (
        <>
          <p>
            Máy:{" "}
            {args.target_ref === "local:windows"
              ? "Máy Windows này (local:windows)"
              : String(args.target_ref ?? "")}
          </p>
          {args.shell != null && <p>Shell: {String(args.shell)}</p>}
          {args.cwd != null && <p>Thư mục: {String(args.cwd)}</p>}
          {args.timeout_seconds != null && (
            <p>Thời gian tối đa: {String(args.timeout_seconds)} giây</p>
          )}
          {args.max_output_bytes != null && (
            <p>Output tối đa: {String(args.max_output_bytes)} byte</p>
          )}
          {args.command_id != null && <p>Lệnh: {String(args.command_id)}</p>}
          {typeof args.command === "string" && (
            <pre
              aria-label="Lệnh chờ xác nhận"
              className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded border p-2"
            >
              {args.command}
            </pre>
          )}
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="flex gap-2">
        <Button type="button" variant="outline" disabled={busy} onClick={() => void decide("deny")}>
          Từ chối
        </Button>
        <Button type="button" disabled={busy || !payload} onClick={() => void decide("allow")}>
          Cho phép lệnh này
        </Button>
      </div>
    </div>
  );
}
