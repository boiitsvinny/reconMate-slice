"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { CommandSessionProvider } from "@/components/intelligence/command-session";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 8_000,
        gcTime: 5 * 60_000,
        retry: 1,
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
        refetchIntervalInBackground: false,
      },
      mutations: { retry: 0 },
    },
  }));

  return <QueryClientProvider client={queryClient}><CommandSessionProvider>{children}</CommandSessionProvider></QueryClientProvider>;
}
