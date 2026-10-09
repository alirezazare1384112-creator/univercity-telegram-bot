import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/vazirmatn/400.css";
import "@fontsource/vazirmatn/700.css";
import "./index.css";
import App from "./App";

// If anything crashes before/during React render, show the error text
// instead of a silent white page (users otherwise just report "صفحه سفید").
function showFatal(message: string) {
  const root = document.getElementById("root");
  if (!root || root.childElementCount > 0) return;
  const escaped = message.replace(/[<>&]/g, (c) =>
    c === "<" ? "&lt;" : c === ">" ? "&gt;" : "&amp;",
  );
  root.innerHTML = `<pre style="white-space:pre-wrap;direction:ltr;padding:16px;font-size:12px;color:#b91c1c;background:#fff7f7;min-height:100vh;margin:0">${escaped}</pre>`;
}
window.addEventListener("error", (e) => {
  showFatal(`JS error:\n${e.message}\n${e.filename}:${e.lineno}:${e.colno}`);
});
window.addEventListener("unhandledrejection", (e) => {
  const reason =
    e.reason instanceof Error
      ? `${e.reason.message}\n${e.reason.stack ?? ""}`
      : String(e.reason);
  showFatal(`Unhandled rejection:\n${reason}`);
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
