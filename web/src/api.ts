import type {
  AiAnalysisResponse,
  AiAnalysisStreamEvent,
  AiChatResponse,
  AiChatStreamEvent,
  BillingPlan,
  ComingSoonResponse,
  ProbeResponse,
} from "./types";

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

export function analyzeVideo(url: string, formatId: string, language = "zh") {
  return requestJson<AiAnalysisResponse>("/api/ai/analyze", {
    method: "POST",
    body: JSON.stringify({ url, format_id: formatId, language }),
  });
}

export async function analyzeVideoStream(
  url: string,
  formatId: string,
  onEvent: (event: AiAnalysisStreamEvent) => void,
  language = "zh",
) {
  const response = await fetch("/api/ai/analyze-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, format_id: formatId, language }),
  });

  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload.detail === "string" ? payload.detail : "AI 分析失败，请稍后重试。";
    if (response.status === 404) {
      onEvent({ type: "status", message: "当前后端暂不支持流式分析，正在切换兼容模式..." });
      const analysis = await analyzeVideo(url, formatId, language);
      onEvent({ type: "summary_delta", delta: analysis.summary });
      onEvent({ type: "complete", analysis });
      return;
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const dataLine = part
        .split("\n")
        .map((line) => line.trim())
        .find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      const raw = dataLine.slice(5).trim();
      if (!raw) continue;
      onEvent(JSON.parse(raw) as AiAnalysisStreamEvent);
    }
  }

  const tail = buffer.trim();
  if (tail.startsWith("data:")) {
    onEvent(JSON.parse(tail.slice(5).trim()) as AiAnalysisStreamEvent);
  }
}

export function chatWithVideo(analysisId: string, question: string) {
  return requestJson<AiChatResponse>("/api/ai/chat", {
    method: "POST",
    body: JSON.stringify({ analysis_id: analysisId, question }),
  });
}

export async function chatWithVideoStream(
  analysisId: string,
  question: string,
  onEvent: (event: AiChatStreamEvent) => void,
) {
  const response = await fetch("/api/ai/chat-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis_id: analysisId, question }),
  });

  if (!response.ok || !response.body) {
    if (response.status === 404) {
      const result = await chatWithVideo(analysisId, question);
      onEvent({ type: "answer_delta", delta: result.answer });
      onEvent({ type: "complete", answer: result.answer, related_segments: result.related_segments, model: result.model });
      return;
    }
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload.detail === "string" ? payload.detail : "AI 问答失败，请稍后重试。";
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const dataLine = part
        .split("\n")
        .map((line) => line.trim())
        .find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      const raw = dataLine.slice(5).trim();
      if (!raw) continue;
      onEvent(JSON.parse(raw) as AiChatStreamEvent);
    }
  }

  const tail = buffer.trim();
  if (tail.startsWith("data:")) {
    onEvent(JSON.parse(tail.slice(5).trim()) as AiChatStreamEvent);
  }
}
