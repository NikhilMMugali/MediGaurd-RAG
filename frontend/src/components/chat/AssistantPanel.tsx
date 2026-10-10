import * as React from "react";
import { Loader2, Paperclip, Send, X } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { queryRag } from "@/api/rag";
import { uploadDocument } from "@/api/documents";
import { ApiError } from "@/api/client";
import { CAN_UPLOAD, ROLE_ASSISTANT_NAME, ROLE_PLACEHOLDER, ROLE_QUICK_PROMPTS } from "@/lib/roles";
import type { Citation, RagStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import ChatMessage from "@/components/chat/ChatMessage";
import SourceViewerPanel from "@/components/documents/SourceViewerPanel";

interface Message {
  role: "user" | "assistant";
  text: string;
  status?: RagStatus;
  citations?: Citation[];
}

interface AssistantPanelProps {
  patientId: string | null;
  onClearPatient: () => void;
  onSelectPatient: (patientId: string) => void;
}

export default function AssistantPanel({ patientId, onClearPatient, onSelectPatient }: AssistantPanelProps) {
  const { user } = useAuth();
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [isUploading, setIsUploading] = React.useState(false);
  const [activeCitation, setActiveCitation] = React.useState<Citation | null>(null);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Without this, switching from Patient A to Patient B (or back to no
  // patient) left Patient A's messages and citations on screen under the
  // new patient badge — each answer is still correctly re-scoped by the
  // backend, but the visible transcript made it look like the old
  // conversation was still about the newly selected patient. A patient
  // switch starts a fresh thread rather than silently mixing two
  // patients' Q&A in one scrollback.
  React.useEffect(() => {
    setMessages([]);
    setActiveCitation(null);
  }, [patientId]);

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

  async function handleFileSelected(file: File) {
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setMessages((prev) => [...prev, { role: "assistant", text: "Only PDF files are supported." }]);
      return;
    }
    setMessages((prev) => [...prev, { role: "user", text: `📎 Uploaded ${file.name}` }]);
    setIsUploading(true);
    try {
      const result = await uploadDocument(file);

      if (result.status === "NEEDS_REVIEW") {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: `I saved **${result.file_name}**, but it looks like a scanned/image-only PDF with no extractable text — OCR isn't supported yet, so it's stored for manual review rather than indexed.`,
          },
        ]);
        return;
      }

      const patientLine = result.patient_id
        ? `for patient **${result.patient_id}**`
        : "but no patient could be identified in it";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text:
            `Processed **${result.file_name}** ${patientLine} — ${result.records_created} record(s) created, ` +
            `${result.chunks_indexed} chunk(s) indexed and ready to search.` +
            (result.patient_id ? " You can now ask questions about this patient below." : ""),
        },
      ]);
      if (result.patient_id) onSelectPatient(result.patient_id);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Upload failed. Please try again.";
      setMessages((prev) => [...prev, { role: "assistant", text: message }]);
    } finally {
      setIsUploading(false);
    }
  }

  const canUpload = CAN_UPLOAD.includes(user.role);

  return (
    <div className="flex h-full min-w-0">
      <div className="flex min-w-0 flex-1 flex-col">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-semibold">{ROLE_ASSISTANT_NAME[user.role]}</h2>
        {patientId && (
          <Badge variant="secondary" className="gap-1.5">
            Patient: {patientId}
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
            {canUpload && (
              <p className="flex items-center gap-1 text-xs">
                <Paperclip className="h-3 w-3" />
                You can also upload a patient PDF using the attach button below.
              </p>
            )}
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
            <ChatMessage
              key={i}
              role={m.role}
              text={m.text}
              status={m.status}
              citations={m.citations}
              onCitationClick={setActiveCitation}
            />
          ))}
          {isLoading && (
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              MediGaurd is thinking...
            </p>
          )}
          {isUploading && (
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Uploading and processing document...
            </p>
          )}
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
        {canUpload && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFileSelected(file);
                e.target.value = "";
              }}
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              disabled={isUploading || isLoading}
              onClick={() => fileInputRef.current?.click()}
              aria-label="Upload a patient PDF"
              title="Upload a patient PDF"
            >
              {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
            </Button>
          </>
        )}
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={patientId ? `Ask about ${patientId}...` : ROLE_PLACEHOLDER[user.role]}
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

      {activeCitation && (
        <div className="fixed inset-0 z-50 bg-background md:static md:inset-auto md:z-auto md:w-[460px] md:shrink-0">
          <SourceViewerPanel citation={activeCitation} onClose={() => setActiveCitation(null)} />
        </div>
      )}
    </div>
  );
}
