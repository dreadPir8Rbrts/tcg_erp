/**
 * Minimal layout for auth-flow pages (login, onboarding).
 * No main nav or sidebar — just the leftovers.gg logo, centred content.
 */

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <div className="mb-8 text-center">
        <span className="font-brand text-base tracking-tight">leftovers<span className="text-emerald-500">.gg</span></span>
      </div>
      {children}
    </div>
  );
}
