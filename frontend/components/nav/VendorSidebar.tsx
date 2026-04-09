"use client";

/**
 * Sidebar navigation for vendor mode.
 * Active link detection via usePathname.
 * Accepts profileId to construct the profile link dynamically.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Package,
  ScanLine,
  CalendarDays,
  ArrowLeftRight,
  UserCircle,
  FlaskConical,
} from "lucide-react";

interface NavLinkProps {
  href: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

function NavLink({ href, label, icon: Icon }: NavLinkProps) {
  const pathname = usePathname();
  const isActive = pathname === href || pathname.startsWith(href + "/");

  return (
    <Link
      href={href}
      className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
        isActive
          ? "bg-accent text-accent-foreground font-medium"
          : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
      }`}
    >
      <Icon size={16} className="shrink-0" />
      {label}
    </Link>
  );
}

interface VendorSidebarProps {
  profileId?: string;
}

export function VendorSidebar({ profileId }: VendorSidebarProps) {
  const p = profileId ?? "";
  const navItems = [
    { href: p ? `/dashboard/${p}` : "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: p ? `/inventory/${p}` : "/inventory", label: "Inventory", icon: Package },
    { href: p ? `/scan/${p}` : "/scan", label: "Scan", icon: ScanLine },
    { href: "/shows", label: "Shows", icon: CalendarDays },
    { href: p ? `/transactions/${p}` : "/transactions", label: "Transactions", icon: ArrowLeftRight },
    { href: p ? `/profile/${p}` : "/profile", label: "Profile", icon: UserCircle },
    { href: "/api-tester", label: "API Tester", icon: FlaskConical },
  ];

  return (
    <aside className="w-56 border-r bg-background shrink-0 flex flex-col gap-1 py-4 px-2 overflow-y-auto">
      {navItems.map((item) => (
        <NavLink key={item.href} {...item} />
      ))}
    </aside>
  );
}
