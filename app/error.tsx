"use client";

import { Button } from "@/components/ui/button";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto w-full max-w-lg px-4 py-16">
      <h1 className="text-2xl font-semibold text-ink">The monitor didn’t load</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">{error.message}</p>
      <Button type="button" className="mt-5" onClick={reset}>
        Try again
      </Button>
    </main>
  );
}
