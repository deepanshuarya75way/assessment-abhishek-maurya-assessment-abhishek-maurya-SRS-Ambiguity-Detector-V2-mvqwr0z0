import { PRIVATE_ROBOTS } from "@/lib/seo";

/**
 * Auth route group — utility pages, never indexed (the project contract).
 * The `m-auto` child centers without clipping tall cards on short viewports.
 */
export const metadata = {
  robots: PRIVATE_ROBOTS,
};

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-dvh bg-paper-deep px-4 py-10 sm:px-6">
      <div className="m-auto flex w-full justify-center">{children}</div>
    </main>
  );
}
