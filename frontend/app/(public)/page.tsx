/**
 * Homepage — placeholder until Task 10 (landing page) is built.
 */

import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function HomePage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-3.5rem)] gap-6 text-center px-4">
      <h1 className="font-brand text-2xl flex items-center" style={{ color: '#FFFFFF', fontWeight: 500, letterSpacing: '0.2px' }}>
        leftovers<span className="text-primary">.gg</span>
      </h1>
      <p className="text-muted-foreground text-lg max-w-md">
        The ERP for TCG vendors and collectors.
      </p>
      <div className="flex gap-3">
        <Button asChild>
          <Link href="/signup">Get Started</Link>
        </Button>
        <Button variant="outline" asChild>
          <Link href="/card-shows">Browse Shows</Link>
        </Button>
      </div>
    </div>
  );
}
