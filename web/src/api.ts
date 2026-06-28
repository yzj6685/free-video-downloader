import type { BillingPlan, ComingSoonResponse, ProbeResponse } from "./types";

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : "请求失败，请稍后重试。";
    throw new Error(detail);
  }

  return payload as T;
}

export function probeVideo(url: string) {
  return requestJson<ProbeResponse>("/api/probe", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function startDownload(url: string, formatId: string) {
  const response = await fetch("/api/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, format_id: formatId, delivery: "direct" }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : "下载失败，请稍后重试。";
    throw new Error(detail);
  }

  return payload as { type: "direct" | "proxy"; url: string; filename: string };
}

export function fetchPlans() {
  return requestJson<{ plans: BillingPlan[] }>("/api/billing/plans").then((data) => data.plans);
}

export function requestComingSoon(path: string) {
  return requestJson<ComingSoonResponse>(path, { method: "POST", body: JSON.stringify({}) });
}
