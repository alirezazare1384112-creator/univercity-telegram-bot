export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <section className="rounded-2xl bg-black/5 p-6 text-center">
      <h1 className="text-lg font-bold">{title}</h1>
      <p className="mt-2 text-sm opacity-70">این صفحه در مرحلهٔ بعد اضافه می‌شود.</p>
    </section>
  );
}
