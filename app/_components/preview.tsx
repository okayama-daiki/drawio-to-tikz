"use client";

import { AlertCircle, Copy } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/app/_components/ui/button";

interface PreviewProps {
  tikzCode: string;
}

export default function Preview({ tikzCode }: PreviewProps) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (copied) {
      const timer = setTimeout(() => setCopied(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [copied]);

  const handleCopyLatex = () => {
    navigator.clipboard.writeText(tikzCode);
    setCopied(true);
  };

  return (
    <div className="bg-card rounded-lg border border-border p-6 shadow-sm">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold text-foreground">Preview</h2>
        <Button
          className="flex items-center gap-2 bg-transparent"
          onClick={handleCopyLatex}
          size="sm"
          variant="outline"
        >
          <Copy className="w-4 h-4" />
          {copied ? "Copied!" : "Copy Code"}
        </Button>
      </div>

      <div className="bg-muted rounded p-6 h-64 flex flex-col items-center justify-center border border-dashed border-border">
        <AlertCircle className="w-8 h-8 text-muted-foreground mb-3" />
        <p className="text-muted-foreground text-center mb-4">
          TikZ rendering requires a LaTeX compiler
        </p>
        <div className="text-xs text-muted-foreground text-center space-y-2">
          <p>Compile your LaTeX document using:</p>
          <p className="font-mono bg-background p-2 rounded">
            pdflatex document.tex
          </p>
          <p className="mt-4">Or use online platforms like:</p>
          <p className="font-semibold text-foreground">Overleaf.com</p>
        </div>
      </div>
    </div>
  );
}
