import * as React from "react";
import { Send, X } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { queryRag } from "@/api/rag";
import { ApiError } from "@/api/client";
import { ROLE_ASSISTANT_NAME, ROLE_PLACEHOLDER, ROLE_QUICK_PROMPTS } from "@/lib/roles";
import type { Citation, RagStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import ChatMessage from "@/components/chat/ChatMessage";

interface Message {
  role: "user" | "assistant";
  text: string;
  status?: RagStatus;
  citations?: Citation[];
}

interface AssistantPanelProps {
  patientId: string | null;
  onClearPatient: () => void;
}

export default function AssistantPanel({ patientId, onClearPatient }: AssistantPanelProps) {
  const { user } = useAuth();
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  if (!user) return null;

  async function send(question: string) {
    if (!question.trim() || isLoading) return;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setIsLoading(true);
    try {
      const result = await queryRag(question, patientId);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: result.answer, status: result.status, citations: result.citations },
      ]);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong while processing your request. Please try again.";
      setMessages((prev) => [...prev, { role: "assistant", text: message, status: "NO_AUTHORIZED_CONTEXT" }]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-semibold">{ROLE_ASSISTANT_NAME[user.role]}</h2>
        {patientId && (
          <Badge variant="secondary" className="gap-1.5">
            Patient: {patientId.length > 12 ? `${patientId.slice(0, 8)}…` : patientId}
            <button onClick={onClearPatient} aria-label="Clear patient context">
              <X className="h-3 w-3" />
            </button>
          </Badge>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-muted-foreground">
            <p>{patientId ? "Ask anything you are authorized to access." : "Select a patient or ask MediGaurd a question."}</p>
            <div className="flex flex-wrap justify-center gap-2">
              {ROLE_QUICK_PROMPTS[user.role].map((prompt) => (
                <Button key={prompt} variant="outline" size="sm" onClick={() => send(prompt)}>
                  {prompt}
                </Button>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-4">
          {messages.map((m, i) => (
            <ChatMessage key={i} role={m.role} text={m.text} status={m.status} citations={m.citations} />
          ))}
          {isLoading && <p className="text-sm text-muted-foreground">MediGaurd is retrieving authorized information...</p>}
        </div>
        <div ref={bottomRef} />
      </div>

      <form
        className="flex items-end gap-2 border-t p-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={ROLE_PLACEHOLDER[user.role]}
          className="min-h-[40px] resize-none"
          rows={1}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
        />
        <Button type="submit" size="icon" disabled={isLoading || !input.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
