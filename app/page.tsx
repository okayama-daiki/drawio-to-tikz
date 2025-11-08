"use client";

import { AlertCircle, Check } from "lucide-react";
import { useState } from "react";
import Editor from "@/app/_components/editor";
import FileUpload from "@/app/_components/file-upload";
import Preview from "@/app/_components/preview";
import { Alert, AlertDescription } from "@/app/_components/ui/alert";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/app/_components/ui/tabs";

export default function Home() {
  const [drawioXml, setDrawioXml] = useState<string>("");
  const [tikzCode, setTikzCode] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [success, setSuccess] = useState(false);

  const handleFileUpload = async (file: File) => {
    setError("");
    setSuccess(false);

    try {
      const text = await file.text();
      setDrawioXml(text);

      // Convert to TikZ
      setIsLoading(true);
      const response = await fetch("/api/convert", {
        body: JSON.stringify({ xml: text }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });

      if (!response.ok) {
        throw new Error("Conversion failed");
      }

      const data = await response.json();
      setTikzCode(data.tikz);
      setSuccess(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "An error occurred during conversion"
      );
      console.error("Conversion error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-background">
      <div className="container mx-auto py-8 px-4">
        {/* Header */}
        <div className="mb-12 text-center">
          <h1 className="text-4xl font-bold text-foreground mb-4">
            Draw.io to TikZ
          </h1>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
            Convert your Draw.io diagrams into professional LaTeX TikZ code.
            Perfect for academic papers and technical documentation.
          </p>
        </div>

        {/* Error and Success Messages */}
        {error && (
          <Alert className="mb-6" variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert className="mb-6 border-green-200 bg-green-50 text-green-800">
            <Check className="h-4 w-4" />
            <AlertDescription>
              Conversion successful! Your TikZ code is ready.
            </AlertDescription>
          </Alert>
        )}

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Panel - Upload and XML */}
          <div className="space-y-4">
            <div className="bg-card rounded-lg border border-border p-6 shadow-sm">
              <h2 className="text-xl font-semibold text-foreground mb-4">
                1. Upload File
              </h2>
              <FileUpload onFileSelect={handleFileUpload} />
              <p className="text-xs text-muted-foreground mt-3">
                Supports .drawio and .xml files exported from Draw.io
              </p>
            </div>

            {drawioXml && (
              <div className="bg-card rounded-lg border border-border p-6 shadow-sm">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-xl font-semibold text-foreground">
                    XML Preview
                  </h2>
                  <span className="text-xs bg-primary/10 text-primary px-2 py-1 rounded">
                    {drawioXml.length} bytes
                  </span>
                </div>
                <div className="bg-muted rounded p-3 max-h-80 overflow-auto border border-border">
                  <pre className="text-xs text-muted-foreground font-mono whitespace-pre-wrap break-words">
                    {drawioXml.substring(0, 1000)}
                    {drawioXml.length > 1000 && "..."}
                  </pre>
                </div>
              </div>
            )}
          </div>

          {/* Right Panel - Output */}
          <div className="space-y-4">
            {isLoading && (
              <div className="bg-card rounded-lg border border-border p-6 shadow-sm">
                <div className="flex items-center justify-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                  <span className="ml-3 text-muted-foreground">
                    Converting...
                  </span>
                </div>
              </div>
            )}

            {tikzCode && !isLoading && (
              <Tabs className="space-y-4" defaultIndex={0}>
                <TabsList>
                  <TabsTrigger> TikZ Code </TabsTrigger>
                  <TabsTrigger> Preview </TabsTrigger>
                </TabsList>

                <TabsContent className="space-y-4">
                  <Editor code={tikzCode} onCodeChange={setTikzCode} />
                </TabsContent>

                <TabsContent className="space-y-4">
                  <Preview tikzCode={tikzCode} />
                </TabsContent>
              </Tabs>
            )}

            {!tikzCode && !isLoading && drawioXml && (
              <div className="bg-card rounded-lg border border-border p-6 shadow-sm text-center">
                <p className="text-muted-foreground">Ready to convert</p>
              </div>
            )}

            {!tikzCode && !isLoading && !drawioXml && (
              <div className="bg-card rounded-lg border border-border p-6 shadow-sm text-center">
                <p className="text-muted-foreground">
                  Upload a Draw.io file to get started
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Footer Info */}
        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="text-center">
            <div className="text-2xl font-bold text-primary mb-2">1</div>
            <p className="text-sm text-muted-foreground">
              Upload your Draw.io file
            </p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-primary mb-2">2</div>
            <p className="text-sm text-muted-foreground">
              Get instant TikZ code
            </p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-primary mb-2">3</div>
            <p className="text-sm text-muted-foreground">
              Use in your LaTeX documents
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
