/** Minimal typing for the official Telegram WebApp script. */

export interface TelegramWebApp {
  initData: string;
  platform?: string;
  version?: string;
  initDataUnsafe: {
    user?: {
      id: number;
      first_name?: string;
      last_name?: string;
      username?: string;
    };
  };
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  isExpanded: boolean;
  viewportHeight: number;
  ready(): void;
  expand(): void;
  close(): void;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  BackButton: {
    show(): void;
    hide(): void;
    onClick(callback: () => void): void;
  };
  MainButton: {
    text: string;
    show(): void;
    hide(): void;
    onClick(callback: () => void): void;
  };
  HapticFeedback: {
    impactOccurred(style: string): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
  };
  onEvent(event: string, callback: (data: unknown) => void): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export function getWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function applyTheme(webApp: TelegramWebApp): void {
  const root = document.documentElement;
  const bg = webApp.themeParams.bg_color;
  const text = webApp.themeParams.text_color;
  if (bg) root.style.setProperty("--tg-bg", bg);
  if (text) root.style.setProperty("--tg-text", text);
  if (bg) webApp.setBackgroundColor(bg);
}

export function initTelegram(): TelegramWebApp | null {
  const webApp = getWebApp();
  if (!webApp) return null;
  webApp.ready();
  applyTheme(webApp);
  return webApp;
}
