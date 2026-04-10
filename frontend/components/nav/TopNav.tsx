"use client";

/**
 * Persistent top navigation bar for the authenticated app shell.
 * Contains: CardOps logo | spacer | RoleToggle | AvatarDropdown
 */

import Link from "next/link";
import { RoleToggle } from "@/components/shared/RoleToggle";
import { AvatarDropdown } from "./AvatarDropdown";
import type { ProfileData } from "@/lib/api/profiles";

interface TopNavProps {
  profile: ProfileData | null;
}

export function TopNav({ profile }: TopNavProps) {
  return (
    <header className="h-14 border-b bg-background flex items-center px-4 gap-4 sticky top-0 z-50 shrink-0">
      <Link href="/" className="font-bold text-lg">
        CardOps
      </Link>
      <div className="flex-1" />
      {profile && <RoleToggle />}
      <AvatarDropdown profile={profile ?? null} />
    </header>
  );
}
