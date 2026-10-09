import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Loader2, Send, Sparkles } from "lucide-react";
import { queryInsights } from "@/api/insights";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const EXAMPLE_QUESTIONS = ["Summarize recent activity and highlight any data gaps.", "What stands out in these numbers?"];

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Evidence-grounded, not a free chatbot: every number the model could
// possibly cite was already computed by SQL in app.rag.insights and handed
// to it as the only source — Groq explains/narrates, it never calculates a
// total of its own (section 6C/6D).
export default function AIInsightSummary() {
  const [question, setQuestion] = React.useState("");
  const [answer, setAnswer] = React.useState<string | null>(null);
  const [generatedAt, setGeneratedAt] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function ask(q: string) {
    if (!q.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await queryInsights(q);
      setAnswer(result.answer);
      setGeneratedAt(result.generated_at);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate a summary. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-card p-4">
      <div className="flex items-center gap-1.5">
        <Sparkles className="h-4 w-4 text-primary" />
        <p className="text-sm font-semibold">Ask about these insights</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {EXAMPLE_QUESTIONS.map((q) => (
          <Button
            key={q}
            variant="outline"
            size="sm"
            disabled={loading}
            onClick={() => {
              setQuestion(q);
              void ask(q);
            }}
          >
            {q}
          </Button>
        ))}
      </div>

      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
      >
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Summarize recent activity and highlight any data gaps."
          className="min-h-[40px] resize-none"
          rows={1}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(question);
            }
          }}
        />
        <Button type="submit" size="icon" disabled={loading || !question.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </form>

      {loading && (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Analyzing verified metrics...
        </p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {answer && !loading && (
        <div className="rounded-md border bg-muted/40 p-3 text-sm">
          <div className="prose-chat">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
          </div>
          {generatedAt && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              Grounded in the verified metrics above · Generated {formatTimestamp(generatedAt)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
