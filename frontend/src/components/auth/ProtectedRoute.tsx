"use client";

/** Authenticated-route foundation. Loading shows a skeleton; signed-out users go to /login. */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/hooks/useAuth";


export function ProtectedRoute({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);

  if (status === "loading" || status === "unauthenticated") {
    return (
      <div
        aria-busy="true"
        aria-label="Loading your workspace"
        className="mx-auto w-full max-w-md rounded-2xl border border-line bg-white p-8 shadow-xl"
      >
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-40 rounded-lg bg-paper-deep" />
          <div className="h-4 w-full rounded bg-paper-deep" />
          <div className="h-4 w-2/3 rounded bg-paper-deep" />
        </div>
      </div>
    );
  }



  return <>{children}</>;
}
