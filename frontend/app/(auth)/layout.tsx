/**
 * Minimal layout for auth-flow pages (login, onboarding).
 * No main nav or sidebar — just the CardOps logo, centred content.
 */

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <div className="mb-8 text-center">
        <span className="text-2xl font-bold tracking-tight">CardOps</span>
      </div>
      {children}
    </div>
  );
}
