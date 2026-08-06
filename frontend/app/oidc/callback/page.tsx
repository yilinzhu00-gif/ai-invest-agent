"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "../../../components/auth-provider";

export default function OidcCallbackPage() {
  const auth = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (auth.status === "authenticated") router.replace("/agent-runs");
  }, [auth.status, router]);

  return <main className="page-shell"><p>正在完成安全登录，请稍候。</p></main>;
}
