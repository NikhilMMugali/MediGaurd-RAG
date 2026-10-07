import * as React from "react";
import { Upload } from "lucide-react";
import { uploadDocument } from "@/api/documents";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";

type Stage = "idle" | "uploading" | "done" | "error";

interface UploadDialogProps {
  onIndexed: (patientHint: string | null) => void;
}

export default function UploadDialog({ onIndexed }: UploadDialogProps) {
  const [open, setOpen] = React.useState(false);
  const [stage, setStage] = React.useState<Stage>("idle");
  const [message, setMessage] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setStage("uploading");
    setMessage(null);
    try {
      const result = await uploadDocument(file);
      setStage("done");
      setMessage(result.message);
      onIndexed(null);
    } catch (err) {
      setStage("error");
      setMessage(err instanceof ApiError ? err.message : "Upload failed. Please try again.");
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setStage("idle");
          setMessage(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Upload className="h-4 w-4" />
          Upload PDF
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload document</DialogTitle>
          <DialogDescription>PDF patient records only.</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            disabled={stage === "uploading"}
            className="text-sm"
          />

          {stage === "uploading" && (
            <div className="flex flex-col gap-2">
              <p className="text-sm text-muted-foreground">Uploading and processing...</p>
              <Progress value={60} />
            </div>
          )}

          {stage === "done" && (
            <div className="rounded-md border bg-emerald-50 p-3 text-sm text-emerald-800">
              <p className="font-medium">Document ready</p>
              <p className="mt-1 text-emerald-700">{message}</p>
            </div>
          )}

          {stage === "error" && <p className="text-sm text-destructive">{message}</p>}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {stage === "done" ? "Close" : "Cancel"}
            </Button>
            {stage !== "done" && (
              <Button onClick={handleUpload} disabled={stage === "uploading"}>
                {stage === "uploading" ? "Processing..." : "Upload & Process"}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
