import { NavLink } from "react-router-dom";

const ITEMS = [
  { to: "/", label: "خانه", icon: "🏠" },
  { to: "/schedule", label: "برنامه", icon: "📅" },
  { to: "/calendar", label: "تقویم", icon: "📆" },
  { to: "/courses", label: "دروس", icon: "📚" },
  { to: "/profile", label: "پروفایل", icon: "👤" },
];

export default function BottomNav() {
  return (
    <nav
      aria-label="ناوبری اصلی"
      className="fixed inset-x-0 bottom-0 z-10 mx-auto w-full max-w-md border-t border-black/10 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur dark:bg-black/80"
    >
      <ul className="grid grid-cols-5">
        {ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                [
                  "flex flex-col items-center gap-0.5 py-2.5 transition-colors",
                  isActive ? "font-bold text-blue-600" : "opacity-60",
                ].join(" ")
              }
            >
              <span className="text-lg leading-none" aria-hidden="true">
                {item.icon}
              </span>
              <span className="text-[11px]">{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
