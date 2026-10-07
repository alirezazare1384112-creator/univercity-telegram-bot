interface Props {
  state: { status: "guest" } | { status: "error"; message: string };
  onRetry: () => void;
}

function Diagnostics() {
  const webApp =
    typeof window !== "undefined" ? window.Telegram?.WebApp : undefined;
  const hashLength =
    typeof window !== "undefined" ? window.location.hash.length : 0;
  return (
    <p className="font-mono text-[11px] opacity-60" dir="ltr">
      script: {webApp ? "OK" : "MISSING"} · hash: {hashLength}ch · initData:{" "}
      {webApp?.initData ? webApp.initData.length : 0}ch · v
      {webApp?.version ?? "?"} · {webApp?.platform ?? "-"}
    </p>
  );
}

export default function ConnectPage({ state, onRetry }: Props) {
  if (state.status === "error") {
    return (
      <section className="flex flex-col gap-3 rounded-2xl bg-black/5 p-6 text-center">
        <h1 className="text-lg font-bold">اتصال ناموفق</h1>
        <p className="text-sm leading-6">{state.message}</p>
        <Diagnostics />
        <button
          type="button"
          onClick={onRetry}
          className="rounded-xl bg-blue-600 px-4 py-2 font-bold text-white active:opacity-80"
        >
          تلاش دوباره
        </button>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-black/5 p-6 text-center">
      <h1 className="text-lg font-bold">دستیار دانشجو</h1>
      <p className="text-sm leading-6">
        این صفحه باید <b>درون تلگرام</b> و از طریق دکمهٔ ربات باز شود تا احراز
        هویت انجام شود.
      </p>
      <Diagnostics />
      <p className="text-xs opacity-70">
        برای توسعه: ربات را اجرا کنید و در تلگرام دکمهٔ Mini App را بزنید.
      </p>
    </section>
  );
}
