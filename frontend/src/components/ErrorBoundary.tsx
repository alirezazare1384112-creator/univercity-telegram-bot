import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Catches render errors and chunk-load failures from lazy `import()`.
 *
 * Without this, a network blip during a chunk download (common on slow
 * mobile) crashes the whole app to a white screen. The boundary renders
 * a retry button that re-imports the chunk.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("ErrorBoundary caught:", error, info);
  }

  handleRetry = (): void => {
    // Force a full reload — the simplest way to re-import all chunks.
    // A soft retry (clearing state) would re-trigger the same failed
    // import() unless the chunk URL changed, which only happens after
    // a deploy.
    window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    const isChunkError =
      this.state.error?.name === "ChunkLoadError" ||
      this.state.error?.message?.includes("Failed to fetch dynamically imported module");
    return (
      <section className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-6 text-center">
        <span className="text-5xl">{isChunkError ? "📶" : "⚠️"}</span>
        <p className="text-sm font-bold">
          {isChunkError ? "بارگذاری صفحه ناموفق بود" : "خطایی رخ داد"}
        </p>
        <p className="max-w-xs text-xs opacity-70">
          {isChunkStory(this.state.error)
            ? "احتمالاً اتصال اینترنت قطع شده. لطفاً دوباره تلاش کن."
            : (this.state.error?.message ?? "خطای ناشناخته")}
        </p>
        <button
          type="button"
          onClick={this.handleRetry}
          className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-bold text-white active:opacity-80"
        >
          تلاش دوباره
        </button>
      </section>
    );
  }
}

function isChunkStory(error: Error | null): boolean {
  if (!error) return false;
  return (
    error.name === "ChunkLoadError" ||
    error.message.includes("Failed to fetch dynamically imported module") ||
    error.message.includes("Importing a module script failed")
  );
}
