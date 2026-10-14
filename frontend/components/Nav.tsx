"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { clearSession, getUser } from "@/lib/api";

export default function Nav() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<{ username: string; role: string } | null>(null);

  useEffect(() => {
    setUser(getUser());
  }, [pathname]);

  const logout = () => {
    clearSession();
    setUser(null);
    router.push("/login");
  };

  const canWrite = user && user.role !== "teacher";
  const isTeacher = user?.role === "teacher";

  return (
    <nav className="border-b bg-white dark:bg-gray-900">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <a href="/" className="font-bold">Time Table Schedule Generator</a>
        {user && !isTeacher && (
          <>
            <a href="/data" className="text-sm hover:underline">Data</a>
            <a href="/schedule/easy" className="text-sm hover:underline">Easy Builder</a>
            <a href="/chat" className="text-sm hover:underline">Chat</a>
            <a href="/analytics" className="text-sm hover:underline">Analytics</a>
          </>
        )}
        {user && isTeacher && (
          <>
            <a href="/teacher" className="text-sm hover:underline">My Schedule</a>
            <a href="/chat" className="text-sm hover:underline">Chat</a>
          </>
        )}
        {canWrite && (
          <>
            <a href="/schedule" className="text-sm hover:underline">Schedule</a>
            <a href="/constraints" className="text-sm hover:underline">Constraints</a>
          </>
        )}
        <span className="flex-1" />
        {user ? (
          <>
            <span className="text-sm text-gray-500">
              {user.username} ({user.role})
            </span>
            <button onClick={logout} className="rounded border px-2 py-1 text-sm">
              Logout
            </button>
          </>
        ) : (
          <a href="/login" className="rounded bg-blue-600 px-3 py-1 text-sm text-white">
            Login
          </a>
        )}
      </div>
    </nav>
  );
}
