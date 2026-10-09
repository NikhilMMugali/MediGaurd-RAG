import * as React from "react";
import { FileQuestion, Loader2, Send } from "lucide-react";
import { queryDocument } from "@/api/documents";
import { ApiError } from "@/api/client";
import type { Citation, RagStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import ChatMessage from "@/components/chat/ChatMessage";
import { EmptyState } from "@/components/common/StateViews";

interface Message {
  role: "user" | "assistant";
  text: string;
  status?: RagStatus;
  citations?: Citation[];
}

interface DocumentQuestionPanelProps {
  documentId: string | null;
  documentName: string | null;
}

const EXAMPLE_PROMPTS = [
  "Summarize this report.",
  "What medications are mentioned in this document?",
  "What findings are recorded in this document?",
  "When was this report created?",
];

export default function DocumentQuestionPanel({ documentId, documentName }: DocumentQuestionPanelProps) {
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    setMessages([]);
  }, [documentId]);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  async function send(question: string) {
    if (!documentId || !question.trim() || isLoading) return;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setIsLoading(true);
    try {
      const result = await queryDocument(documentId, question);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: result.answer, status: result.status, citations: result.citations },
      ]);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Something went wrong while processing your request. Please try again.";
      setMessages((prev) => [...prev, { role: "assistant", text: message, status: "NO_AUTHORIZED_CONTEXT" }]);
    } finally {
      setIsLoading(false);
    }
  }

  if (!documentId) {
    return (
      <EmptyState
        icon={FileQuestion}
        title="Select a document to ask about it"
        description="Choose a document from the list to ask questions grounded only in its own authorized content."
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-1 pb-2">
        <p className="truncate text-sm font-medium">{documentName}</p>
      </div>

      <div className="flex-1 overflow-y-auto py-3">
        {messages.length === 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground">Ask anything about this document.</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_PROMPTS.map((p) => (
                <Button key={p} variant="outline" size="sm" onClick={() => send(p)}>
                  {p}
                </Button>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-4">
          {messages.map((m, i) => (
            <ChatMessage key={i} role={m.role} text={m.text} status={m.status} citations={m.citations} />
          ))}
          {isLoading && (
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Reading document...
            </p>
          )}
        </div>
        <div ref={bottomRef} />
      </div>

      <form
        className="flex items-end gap-2 border-t pt-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this document..."
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
