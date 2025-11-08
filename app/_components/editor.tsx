"use client";

import { Copy, Download, FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/app/_components/ui/button";
import {
  downloadLatexDocument,
  downloadTikzFile,
} from "@/app/_lib/file-handler";

interface EditorProps {
  code: string;
  onCodeChange: (code: string) => void;
}

export default function Editor({ code, onCodeChange }: EditorProps) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (copied) {
      const timer = setTimeout(() => setCopied(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [copied]);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
  };

  const handleDownloadTikz = () => {
    downloadTikzFile(code);
  };

  const handleDownloadLatex = () => {
    downloadLatexDocument(code);
  };

  return (
    <div className="bg-card rounded-lg border border-border p-6 shadow-sm">
      <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
        <h2 className="text-xl font-semibold text-foreground">TikZ Code</h2>
        <div className="flex gap-2 flex-wrap">
          <Button
            className="flex items-center gap-2 bg-transparent"
            onClick={handleCopy}
            size="sm"
            variant="outline"
          >
            <Copy className="w-4 h-4" />
            {copied ? "Copied!" : "Copy"}
          </Button>
          <Button
            className="flex items-center gap-2 bg-transparent"
            onClick={handleDownloadTikz}
            size="sm"
            variant="outline"
          >
            <Download className="w-4 h-4" />
            .tikz
          </Button>
          <Button
            className="flex items-center gap-2 bg-transparent"
            onClick={handleDownloadLatex}
            size="sm"
            variant="outline"
          >
            <FileText className="w-4 h-4" />
            .tex
          </Button>
        </div>
      </div>
      <textarea
        className="w-full h-96 bg-muted rounded p-4 font-mono text-sm text-foreground border border-border resize-none focus:outline-none focus:ring-2 focus:ring-primary"
        onChange={(e) => onCodeChange(e.target.value)}
        placeholder="TikZ code will appear here"
        value={code}
      />
    </div>
  );
}
