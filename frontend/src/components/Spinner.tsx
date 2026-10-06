export default function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl bg-black/5 p-8 text-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-current border-t-transparent" />
      <p className="text-sm">{label ?? "در حال اتصال به دستیار دانشجو…"}</p>
    </div>
  );
}
