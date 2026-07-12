import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import { Sparkles, Send, Terminal, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Infrastructure Agent" },
      { name: "description", content: "Infrastructure Investigation Platform" },
    ],
  }),
  component: ChatPage,
});

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8080";

type Message = {
  role: "user" | "assistant";
  content: string;
  intent?: string;
  target?: string;
  evidence_count?: number;
};

function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "Gõ câu hỏi để bắt đầu điều tra hạ tầng.\n\nVí dụ:\n- Đánh giá sức khỏe của localhost\n- Zabbix đang có vấn đề gì?\n- Có service nào bị lỗi?\n- Security baseline có tốt không?",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit() {
    const question = input.trim();
    if (!question || loading) return;

    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(err);
      }

      const data = await res.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.assessment || "(empty response)",
          intent: data.intent,
          target: data.target,
          evidence_count: data.evidence_count,
        },
      ]);
    } catch (err: any) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <header className="h-14 border-b border-border flex items-center gap-3 px-4 shrink-0 bg-card">
        <Terminal className="h-5 w-5 text-primary" />
        <span className="text-sm font-semibold">Infrastructure Agent</span>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] ${msg.role === "user" ? "order-1" : "order-1"}`}>
                {msg.role === "user" ? (
                  <div className="bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm">
                    {msg.content}
                  </div>
                ) : (
                  <Card className="p-4 border-border/50">
                    {msg.intent && (
                      <div className="flex flex-wrap gap-2 mb-3 text-[11px] text-muted-foreground">
                        <span className="bg-muted px-2 py-0.5 rounded">{msg.intent}</span>
                        {msg.target && <span className="bg-muted px-2 py-0.5 rounded">target: {msg.target}</span>}
                        {msg.evidence_count !== undefined && (
                          <span className="bg-muted px-2 py-0.5 rounded">{msg.evidence_count} evidence items</span>
                        )}
                      </div>
                    )}
                    <div className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                  </Card>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <Card className="p-4 border-border/50">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span className="animate-spin h-4 w-4 border-2 border-primary border-t-transparent rounded-full" />
                  Đang điều tra...
                </div>
              </Card>
            </div>
          )}

          {error && (
            <div className="flex justify-center">
              <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 px-4 py-2 rounded-lg">
                <AlertCircle className="h-4 w-4" />
                {error}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-border bg-card px-4 py-4">
        <div className="mx-auto max-w-3xl flex gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Hỏi về hạ tầng..."
            className="min-h-[44px] max-h-[120px] resize-none text-sm"
            rows={1}
            disabled={loading}
          />
          <Button
            onClick={handleSubmit}
            disabled={loading || !input.trim()}
            size="icon"
            className="h-[44px] w-[44px] shrink-0"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
