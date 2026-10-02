import { type RuntimeEvent } from "@/lib/chat-store";

export function parseSseEvents(buffer: string): { events: RuntimeEvent[]; remainder: string } {
  const frames = buffer.split("\n\n");
  const remainder = frames.pop() || "";
  const events = frames.flatMap((frame): RuntimeEvent[] => {
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("\n");
    if (!data) return [];
    try {
      const parsed = JSON.parse(data) as RuntimeEvent;
      return typeof parsed.type === "string" && parsed.payload ? [parsed] : [];
    } catch {
      return [];
    }
  });
  return { events, remainder };
}
