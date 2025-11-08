"use client";

import type * as React from "react";

// Lightweight passthrough ThemeProvider to avoid next-themes dependency
export type ThemeProviderProps = {
  children: React.ReactNode;
  // Accept any props but ignore them; extend later if theming is reintroduced
  [key: string]: unknown;
};

export function ThemeProvider({ children }: ThemeProviderProps) {
  return <>{children}</>;
}
