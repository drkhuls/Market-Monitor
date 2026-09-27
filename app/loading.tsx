export default function Loading() {
  return (
    <main className="mx-auto w-full max-w-[1180px] px-4 py-6 sm:px-6 sm:py-8">
      <div className="h-4 w-16 rounded bg-white" />
      <div className="mt-3 h-10 w-64 rounded bg-white" />
      <div className="mt-3 h-4 w-96 max-w-full rounded bg-white" />
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <div className="h-[420px] rounded-2xl bg-white" />
        <div className="h-[420px] rounded-2xl bg-white" />
      </div>
      <div className="mt-8 h-72 rounded-2xl bg-white" />
      <p className="mt-4 text-sm text-muted">Collecting prices and the latest weekly readings…</p>
    </main>
  );
}
