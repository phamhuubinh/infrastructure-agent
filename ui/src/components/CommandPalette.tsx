import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandItem,
  CommandGroup,
  CommandEmpty,
} from "@/components/ui/command";
import { useChat } from "@/lib/chat-store";
import { MessageSquare, Plus } from "lucide-react";

export function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const { sessions, currentSessionId, startNewChat, switchSession } = useChat();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const filtered = search
    ? sessions.filter((s) => s.title.toLowerCase().includes(search.toLowerCase()))
    : sessions;

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="Tìm kiếm hội thoại hoặc gõ lệnh..."
        value={search}
        onValueChange={setSearch}
      />
      <CommandList>
        <CommandEmpty>Không tìm thấy kết quả.</CommandEmpty>
        <CommandGroup heading="Thao tác">
          <CommandItem
            onSelect={() => {
              startNewChat();
              void navigate({ to: "/" });
              setOpen(false);
              setSearch("");
            }}
          >
            <Plus className="h-4 w-4 mr-2" />
            Tạo hội thoại mới
          </CommandItem>
        </CommandGroup>
        {filtered.length > 0 && (
          <CommandGroup heading="Hội thoại">
            {filtered.map((s) => (
              <CommandItem
                key={s.id}
                onSelect={() => {
                  switchSession(s.id);
                  setOpen(false);
                  setSearch("");
                }}
              >
                <MessageSquare className="h-4 w-4 mr-2" />
                <span className={s.id === currentSessionId ? "font-medium" : ""}>{s.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
