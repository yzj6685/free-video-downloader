<script setup lang="ts">
import {
  ArrowDownToLine,
  BadgeCheck,
  BookOpen,
  BrainCircuit,
  Captions,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  Crown,
  Download,
  FileText,
  ImageDown,
  Languages,
  Loader2,
  Maximize2,
  MessageCircle,
  LockKeyhole,
  Play,
  Search,
  Send,
  Sparkles,
  WandSparkles,
  X,
  Zap,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { analyzeVideoStream, chatWithVideoStream, fetchPlans, probeVideo, requestComingSoon, startDownload } from "./api";
import type { AiAnalysisResponse, AiChatMessage, BillingPlan, ProbeResponse } from "./types";

const videoUrl = ref("");
const selectedFormat = ref("best");
const probeResult = ref<ProbeResponse | null>(null);
const status = ref<"idle" | "probing" | "ready" | "downloading" | "error">("idle");
const message = ref("支持公开视频链接，粘贴后即可解析。");
const plans = ref<BillingPlan[]>([]);
const showPlans = ref(false);
const showToast = ref(false);
const toastText = ref("");
const aiStatus = ref<"idle" | "analyzing" | "ready" | "error">("idle");
const aiMessage = ref("解析视频后，可提取平台字幕并生成 AI 内容摘要。");
const aiResult = ref<AiAnalysisResponse | null>(null);
const aiStreamingSummary = ref("");
const aiActiveTab = ref<"summary" | "transcript" | "mindmap" | "chat">("summary");
const aiQuestion = ref("");
const aiChatStatus = ref<"idle" | "asking">("idle");
const aiChatHistory = ref<AiChatMessage[]>([]);
const showSubtitleMenu = ref(false);
const showMindMapLightbox = ref(false);

type MarkdownBlock =
  | { type: "heading"; level: 2 | 3 | 4; text: string }
  | { type: "paragraph"; html: string }
  | { type: "quote"; html: string }
  | { type: "list"; ordered: boolean; items: string[]; start?: number; nested?: boolean }
  | { type: "code"; text: string };

interface MindMapNode {
  title: string;
  start?: number | null;
  summary: string;
  children: string[];
}

const canProbe = computed(() => videoUrl.value.trim().length > 5 && status.value !== "probing");
const activeFormat = computed(() => selectedFormat.value || probeResult.value?.recommended_format_id || "best");
const thumbnailUrl = computed(() => {
  if (!probeResult.value?.thumbnail) return "";
  const params = new URLSearchParams({
    url: probeResult.value.thumbnail,
    source_url: probeResult.value.url,
  });
  return `/api/media/thumbnail?${params.toString()}`;
});
const previewVideoUrl = computed(() => {
  if (!probeResult.value || thumbnailUrl.value) return "";
  const params = new URLSearchParams({
    url: probeResult.value.url,
    format_id: probeResult.value.recommended_format_id,
  });
  return `/api/media/video-preview?${params.toString()}`;
});
const transcriptText = computed(() => {
  if (!aiResult.value) return "";
  return aiResult.value.transcript_segments
    .map((segment) => `[${formatTimestamp(segment.start)}] ${segment.text}`)
    .join("\n");
});
const summaryBlocks = computed(() => parseMarkdown(aiResult.value?.summary || aiStreamingSummary.value));
const mindMapNodes = computed(() => (aiResult.value ? buildMindMapNodes(aiResult.value) : []));
const mindMapSvg = computed(() => (aiResult.value ? buildMindMapSvg(aiResult.value, mindMapNodes.value) : ""));
const mindMapDataUrl = computed(() => {
  if (!mindMapSvg.value) return "";
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(mindMapSvg.value)}`;
});
const chatQuestionOptions = computed(() => {
  const suggested = aiResult.value?.suggested_questions.filter(Boolean) ?? [];
  return (suggested.length ? suggested : quickChatQuestions).slice(0, 3);
});

const platformCards = [
  { title: "公开课程", tag: "学习复盘", tone: "bg-coral/12 text-coral", desc: "把公开课程和讲座保存到本地，通勤路上也能看。" },
  { title: "短视频素材", tag: "创作归档", tone: "bg-aqua/14 text-aqua", desc: "保存本人或已授权素材，剪辑、复盘、二创更顺手。" },
  { title: "高清视频", tag: "格式选择", tone: "bg-grape/12 text-grape", desc: "解析可用格式，清晰度、扩展名和音视频状态一眼看清。" },
  { title: "移动端下载", tag: "手机可用", tone: "bg-mint/18 text-emerald-700", desc: "响应式页面，手机浏览器粘贴链接也能完成下载。" },
  { title: "字幕翻译", tag: "会员能力", tone: "bg-honey/18 text-amber-700", desc: "后续支持字幕提取、翻译和双语字幕下载。" },
  { title: "视频总结", tag: "AI 加值", tone: "bg-ink/8 text-ink", desc: "后续接入第三方 AI，把长视频压缩成可复习摘要。" },
];

const advancedActions = [
  { title: "视频总结", desc: "把长视频变成重点摘要", icon: WandSparkles, path: "/api/ai/summary" },
  { title: "字幕翻译", desc: "提取并生成双语字幕", icon: Languages, path: "/api/ai/translate-subtitles" },
  { title: "音频提取", desc: "课程和播客一键转音频", icon: Captions, path: "" },
  { title: "批量队列", desc: "多链接自动排队下载", icon: Zap, path: "" },
];
const aiTabs = [
  { key: "summary", label: "总结摘要", icon: BookOpen },
  { key: "transcript", label: "字幕文本", icon: Captions },
  { key: "mindmap", label: "思维导图", icon: BrainCircuit },
  { key: "chat", label: "AI 问答", icon: MessageCircle },
] as const;
const quickChatQuestions = ["这个视频主要讲了什么？", "帮我提炼适合复习的重点", "有哪些容易混淆的地方？"];

function formatDuration(seconds?: number | null) {
  if (!seconds) return "未知时长";
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function formatSize(bytes?: number | null) {
  if (!bytes) return "大小未知";
  if (bytes > 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTimestamp(seconds?: number | null) {
  if (seconds === null || seconds === undefined) return "--:--";
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function formatSubtitleTimestamp(seconds: number, separator: "," | ".") {
  const safeSeconds = Math.max(0, seconds || 0);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const wholeSeconds = Math.floor(safeSeconds % 60);
  const milliseconds = Math.floor((safeSeconds - Math.floor(safeSeconds)) * 1000);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(wholeSeconds).padStart(2, "0")}${separator}${String(milliseconds).padStart(3, "0")}`;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeXml(value: string) {
  return escapeHtml(value);
}

function renderInlineMarkdown(value: string) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code class="rounded bg-ink/8 px-1.5 py-0.5 text-[0.92em] font-bold text-ink">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-black text-ink">$1</strong>')
    .replace(/__([^_]+)__/g, '<strong class="font-black text-ink">$1</strong>');
}

function parseMarkdown(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let listOrdered = false;
  let listStart = 1;
  let listNested = false;
  let orderedSequence = 0;
  let codeLines: string[] = [];
  let inCode = false;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push({ type: "paragraph", html: renderInlineMarkdown(paragraph.join(" ")) });
    paragraph = [];
  };
  const flushList = () => {
    if (!listItems.length) return;
    blocks.push({
      type: "list",
      ordered: listOrdered,
      items: listItems.map(renderInlineMarkdown),
      start: listOrdered ? listStart : undefined,
      nested: listNested,
    });
    listItems = [];
    listNested = false;
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const indent = rawLine.match(/^\s*/)?.[0].length ?? 0;
    if (line.startsWith("```")) {
      if (inCode) {
        blocks.push({ type: "code", text: codeLines.join("\n") });
        codeLines = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeLines.push(rawLine);
      continue;
    }
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({
        type: "heading",
        level: Math.min(4, Math.max(2, heading[1].length + 1)) as 2 | 3 | 4,
        text: heading[2],
      });
      continue;
    }

    if (line.startsWith(">")) {
      flushParagraph();
      flushList();
      blocks.push({ type: "quote", html: renderInlineMarkdown(line.replace(/^>\s?/, "")) });
      continue;
    }

    const bullet = /^[-*•·●]\s+(.+)$/.exec(line);
    const ordered = /^(\d+)[.)]\s+(.+)$/.exec(line);
    if (bullet || ordered) {
      flushParagraph();
      const orderedNow = Boolean(ordered);
      if (listItems.length && listOrdered !== orderedNow) flushList();
      listOrdered = orderedNow;
      if (ordered) {
        const rawStart = Number(ordered[1]);
        if (!listItems.length) {
          listStart = rawStart > orderedSequence ? rawStart : orderedSequence + 1;
          listNested = false;
          orderedSequence = listStart;
        } else {
          orderedSequence += 1;
        }
        listItems.push(ordered[2]);
      } else {
        if (!listItems.length) {
          const previousBlock = blocks[blocks.length - 1];
          listNested = indent > 0 || (previousBlock?.type === "list" && previousBlock.ordered);
        }
        listItems.push(bullet?.[1] ?? line);
      }
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  flushParagraph();
  flushList();
  if (inCode || codeLines.length) blocks.push({ type: "code", text: codeLines.join("\n") });
  return blocks;
}

function wrapText(value: string, limit: number, maxLines = 4) {
  const text = value.replace(/\s+/g, " ").trim();
  if (!text) return [""];
  const lines: string[] = [];
  let current = "";
  for (const char of text) {
    if ((current + char).length > limit) {
      lines.push(current);
      current = char;
    } else {
      current += char;
    }
  }
  if (current) lines.push(current);
  const visible = lines.slice(0, maxLines);
  if (lines.length > maxLines) {
    visible[maxLines - 1] = `${visible[maxLines - 1].slice(0, Math.max(1, limit - 1))}…`;
  }
  return visible;
}

function svgTextLines(
  text: string,
  x: number,
  y: number,
  maxChars: number,
  size = 24,
  weight = 800,
  color = "#161612",
  anchor: "start" | "middle" | "end" = "start",
  maxLines = 3,
) {
  return wrapText(text, maxChars, maxLines)
    .map((line, index) => `<text x="${x}" y="${y + index * (size + 8)}" text-anchor="${anchor}" font-size="${size}" font-weight="${weight}" fill="${color}" font-family="Inter, Arial, sans-serif">${escapeXml(line)}</text>`)
    .join("");
}

function conciseText(value: string, maxLength = 30) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return text;
  const sentence = text.split(/[。！？.!?；;]/)[0]?.trim();
  const picked = sentence && sentence.length >= 4 ? sentence : text;
  return picked.length > maxLength ? `${picked.slice(0, maxLength)}…` : picked;
}

function buildMindMapNodes(analysis: AiAnalysisResponse): MindMapNode[] {
  if (analysis.outline.length) {
    return analysis.outline.slice(0, 8).map((item) => ({
      title: conciseText(item.title, 22),
      start: item.start,
      summary: conciseText(item.summary, 42),
      children: item.summary ? wrapText(item.summary, 16, 2).filter(Boolean) : [],
    }));
  }

  const segments = analysis.transcript_segments;
  if (!segments.length) {
    return [{ title: "暂无字幕内容", summary: "生成摘要后可查看导图", children: [] }];
  }

  const groupCount = Math.min(6, Math.max(3, Math.ceil(segments.length / 18)));
  const groupSize = Math.ceil(segments.length / groupCount);
  const nodes: MindMapNode[] = [];
  for (let index = 0; index < groupCount; index += 1) {
    const group = segments.slice(index * groupSize, (index + 1) * groupSize);
    if (!group.length) continue;
    const title = conciseText(group[0].text, 18);
    const childSource = group.filter((_, itemIndex) => itemIndex % Math.max(1, Math.floor(group.length / 3)) === 0).slice(0, 3);
    nodes.push({
      title,
      start: group[0].start,
      summary: conciseText(group.map((segment) => segment.text).join(" "), 42),
      children: childSource.map((segment) => conciseText(segment.text, 14)),
    });
  }
  return nodes;
}

function svgBranchLabel(
  text: string,
  x: number,
  y: number,
  side: "left" | "right",
  color: string,
  size = 26,
  maxChars = 13,
) {
  const anchor = side === "left" ? "end" : "start";
  const underlineEnd = side === "left" ? x - 250 : x + 250;
  return `
    <line x1="${x}" y1="${y + 10}" x2="${underlineEnd}" y2="${y + 10}" stroke="${color}" stroke-width="3" stroke-linecap="round" opacity="0.75"/>
    ${svgTextLines(text, x, y, maxChars, size, 700, "#4d4a45", anchor, 2)}
  `;
}

function buildMindMapSvg(analysis: AiAnalysisResponse, nodes: MindMapNode[]) {
  const visibleNodes = nodes.slice(0, 8);
  const leftNodes = visibleNodes.filter((_, index) => index % 2 === 1);
  const rightNodes = visibleNodes.filter((_, index) => index % 2 === 0);
  const rows = Math.max(leftNodes.length, rightNodes.length, 3);
  const width = 2200;
  const height = Math.max(1080, rows * 280 + 320);
  const centerX = 1100;
  const centerY = Math.round(height / 2);
  const palette = ["#2f80ed", "#27b6bd", "#7c5cff", "#e05243", "#d98b25", "#7aa833", "#a35aa8", "#8b5a42"];

  const renderSide = (sideNodes: MindMapNode[], side: "left" | "right") => {
    const isLeft = side === "left";
    const branchX = isLeft ? centerX - 410 : centerX + 410;
    const labelX = isLeft ? branchX - 70 : branchX + 70;
    const startY = centerY - ((sideNodes.length - 1) * 250) / 2;
    return sideNodes
      .map((node, sideIndex) => {
        const globalIndex = visibleNodes.indexOf(node);
        const color = palette[globalIndex % palette.length];
        const y = startY + sideIndex * 250;
        const c1x = isLeft ? centerX - 190 : centerX + 190;
        const c2x = isLeft ? branchX + 150 : branchX - 150;
        const childBaseX = isLeft ? labelX - 330 : labelX + 330;
        const children = node.children.slice(0, 4).map((child, childIndex) => {
          const childY = y + 66 + childIndex * 62;
          const curveEndX = isLeft ? childBaseX + 38 : childBaseX - 38;
          return `
            <path d="M ${labelX} ${y + 16} C ${isLeft ? labelX - 92 : labelX + 92} ${y + 58}, ${isLeft ? curveEndX + 92 : curveEndX - 92} ${childY}, ${curveEndX} ${childY}" stroke="${color}" stroke-width="2.5" fill="none" opacity="0.6"/>
            <circle cx="${curveEndX}" cy="${childY}" r="8" fill="#fffaf0" stroke="${color}" stroke-width="4"/>
            ${svgBranchLabel(child, childBaseX, childY - 8, side, color, 22, 11)}
          `;
        });
        return `
          <path d="M ${centerX} ${centerY} C ${c1x} ${centerY}, ${c2x} ${y}, ${branchX} ${y}" stroke="${color}" stroke-width="4" fill="none" stroke-linecap="round"/>
          <circle cx="${branchX}" cy="${y}" r="12" fill="#fffaf0" stroke="${color}" stroke-width="5"/>
          ${svgBranchLabel(node.title, labelX, y - 8, side, color, 28, 14)}
          <text x="${isLeft ? labelX - 118 : labelX + 118}" y="${y + 44}" text-anchor="${isLeft ? "end" : "start"}" font-size="18" font-weight="800" fill="${color}" font-family="Inter, Arial, sans-serif">${node.start === null || node.start === undefined ? "" : formatTimestamp(node.start)}</text>
          ${children.join("")}
        `;
      })
      .join("");
  };

  return `
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#fffaf0"/>
      <stop offset="52%" stop-color="#fffdf8"/>
      <stop offset="100%" stop-color="#eef9ff"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#161612" flood-opacity="0.12"/>
    </filter>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="280" cy="160" r="230" fill="#ff6b5f" fill-opacity="0.10"/>
  <circle cx="1900" cy="170" r="270" fill="#5bc0eb" fill-opacity="0.14"/>
  <g filter="url(#shadow)">
    <rect x="${centerX - 250}" y="${centerY - 96}" width="500" height="192" rx="42" fill="#ffffff"/>
    <text x="${centerX}" y="${centerY - 34}" text-anchor="middle" font-size="24" font-weight="900" fill="#7c5cff" font-family="Inter, Arial, sans-serif">视频主题</text>
    ${svgTextLines(analysis.title, centerX, centerY + 10, 16, 30, 900, "#161612", "middle", 2)}
  </g>
  ${renderSide(leftNodes, "left")}
  ${renderSide(rightNodes, "right")}
</svg>`.trim();
}

function sanitizeFilename(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, "_").replace(/\s+/g, " ").trim().slice(0, 80) || "video";
}

function downloadBlob(content: BlobPart, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 500);
}

function buildSubtitle(format: "srt" | "vtt" | "txt") {
  if (!aiResult.value) return "";
  const segments = aiResult.value.transcript_segments;
  if (format === "txt") return transcriptText.value;
  const body = segments
    .map((segment, index) => {
      const end = segment.end ?? segments[index + 1]?.start ?? segment.start + 3;
      if (format === "vtt") {
        return `${formatSubtitleTimestamp(segment.start, ".")} --> ${formatSubtitleTimestamp(end, ".")}\n${segment.text}`;
      }
      return `${index + 1}\n${formatSubtitleTimestamp(segment.start, ",")} --> ${formatSubtitleTimestamp(end, ",")}\n${segment.text}`;
    })
    .join("\n\n");
  return format === "vtt" ? `WEBVTT\n\n${body}\n` : `${body}\n`;
}

function downloadSubtitle(format: "srt" | "vtt" | "txt") {
  if (!aiResult.value) return;
  const filename = `${sanitizeFilename(aiResult.value.title)}.${format}`;
  const contentType = format === "txt" ? "text/plain;charset=utf-8" : `text/${format};charset=utf-8`;
  downloadBlob(buildSubtitle(format), filename, contentType);
  showSubtitleMenu.value = false;
  showNotice(`已生成 ${format.toUpperCase()} 字幕文件。`);
}

async function downloadMindMapPng() {
  if (!aiResult.value || !mindMapSvg.value) return;
  const image = new Image();
  image.decoding = "async";
  const svgUrl = URL.createObjectURL(new Blob([mindMapSvg.value], { type: "image/svg+xml;charset=utf-8" }));
  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("思维导图图片生成失败，请稍后重试。"));
      image.src = svgUrl;
    });
    const scale = 2;
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth * scale;
    canvas.height = image.naturalHeight * scale;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("当前浏览器不支持图片导出。");
    context.fillStyle = "#fffaf0";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png", 1));
    if (!blob) throw new Error("思维导图图片生成失败，请稍后重试。");
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${sanitizeFilename(aiResult.value.title)}-mindmap.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 500);
    showNotice("高清思维导图已开始下载。");
  } catch (error) {
    showNotice(error instanceof Error ? error.message : "思维导图图片生成失败，请稍后重试。");
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text) videoUrl.value = text.trim();
  } catch {
    showNotice("浏览器未授权读取剪贴板，请手动粘贴链接。");
  }
}

async function handleProbe() {
  if (!canProbe.value) return;
  status.value = "probing";
  message.value = "正在解析视频信息，请稍等...";
  probeResult.value = null;

  try {
    const result = await probeVideo(videoUrl.value.trim());
    probeResult.value = result;
    selectedFormat.value = result.recommended_format_id;
    aiStatus.value = "idle";
    aiResult.value = null;
    aiStreamingSummary.value = "";
    aiChatHistory.value = [];
    aiMessage.value = "解析成功后，可继续生成 AI 内容摘要。";
    status.value = "ready";
    message.value = "解析成功，选择格式后即可下载。";
  } catch (error) {
    status.value = "error";
    message.value = error instanceof Error ? error.message : "解析失败，请稍后重试。";
  }
}

async function handleDownload() {
  if (!probeResult.value) return;
  status.value = "downloading";
  message.value = "正在准备下载链接...";

  try {
    const result = await startDownload(probeResult.value.url, activeFormat.value);
    const link = document.createElement("a");
    link.href = result.url;
    link.download = result.filename || "video.mp4";
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
    status.value = "ready";
    message.value = `已生成下载链接：${result.filename}`;
  } catch (error) {
    status.value = "error";
    message.value = error instanceof Error ? error.message : "下载失败，请稍后重试。";
  }
}

async function handleAnalyze() {
  if (!probeResult.value) {
    showNotice("请先解析一个视频，再生成 AI 内容摘要。");
    return;
  }

  aiStatus.value = "analyzing";
  aiMessage.value = "正在提取平台字幕...";
  aiResult.value = null;
  aiStreamingSummary.value = "";
  aiChatHistory.value = [];
  aiActiveTab.value = "summary";

  try {
    await analyzeVideoStream(probeResult.value.url, activeFormat.value, (event) => {
      if (event.type === "status") {
        aiMessage.value = event.message;
        return;
      }
      if (event.type === "transcript_ready") {
        aiMessage.value = `已提取 ${event.transcript_count} 段字幕，正在生成总结...`;
        return;
      }
      if (event.type === "summary_delta") {
        aiStreamingSummary.value += event.delta;
        aiMessage.value = "AI 正在生成总结，可先阅读已输出内容。";
        return;
      }
      if (event.type === "complete") {
        aiResult.value = event.analysis;
    aiStreamingSummary.value = event.analysis.summary || aiStreamingSummary.value;
        aiStatus.value = "ready";
        aiMessage.value = "视频总结已生成，字幕、思维导图和 AI 问答已可使用。";
        return;
      }
      if (event.type === "error") {
        throw new Error(event.message);
      }
    });
    if (!aiResult.value) {
      throw new Error("AI 分析没有返回完整结果，请稍后重试。");
    }
    aiStatus.value = "ready";
    aiMessage.value = "视频总结已生成，字幕、思维导图和 AI 问答已可使用。";
  } catch (error) {
    aiStatus.value = "error";
    aiMessage.value = error instanceof Error ? error.message : "AI 分析失败，请稍后重试。";
  }
}

async function handleAskAi(question?: string) {
  const finalQuestion = (question || aiQuestion.value).trim();
  if (!aiResult.value || !finalQuestion || aiChatStatus.value === "asking") return;

  aiChatStatus.value = "asking";
  aiQuestion.value = "";
  const historyIndex = aiChatHistory.value.length;
  aiChatHistory.value.push({
    question: finalQuestion,
    answer: "",
    related_segments: [],
  });
  try {
    await chatWithVideoStream(aiResult.value.analysis_id, finalQuestion, (event) => {
      const current = aiChatHistory.value[historyIndex];
      if (!current) return;
      if (event.type === "related_segments") {
        current.related_segments = event.related_segments;
        return;
      }
      if (event.type === "answer_delta") {
        current.answer += event.delta;
        return;
      }
      if (event.type === "complete") {
        current.answer = event.answer || current.answer;
        current.related_segments = event.related_segments;
        return;
      }
      if (event.type === "error") {
        throw new Error(event.message);
      }
    });
  } catch (error) {
    aiChatHistory.value.splice(historyIndex, 1);
    showNotice(error instanceof Error ? error.message : "AI 问答失败，请稍后重试。");
  } finally {
    aiChatStatus.value = "idle";
  }
}

async function handleAdvanced(path: string, title: string) {
  if (title === "视频总结") {
    await handleAnalyze();
    return;
  }

  if (!path) {
    showPlans.value = true;
    showNotice(`${title} 是会员高级能力，首版暂未开放。`);
    return;
  }

  try {
    await requestComingSoon(path);
  } catch (error) {
    showPlans.value = true;
    showNotice(error instanceof Error ? error.message : `${title} 即将开放。`);
  }
}

async function copyTranscript() {
  if (!transcriptText.value) return;
  try {
    await navigator.clipboard.writeText(transcriptText.value);
    showNotice("转录文本已复制。");
  } catch {
    showNotice("浏览器未授权写入剪贴板，请手动选择复制。");
  }
}

function showNotice(text: string) {
  toastText.value = text;
  showToast.value = true;
  window.setTimeout(() => {
    showToast.value = false;
  }, 3200);
}

onMounted(async () => {
  try {
    plans.value = await fetchPlans();
  } catch {
    plans.value = [];
  }
});
</script>

<template>
  <main class="min-h-screen overflow-x-hidden">
    <header class="section-shell sticky top-0 z-30 py-4">
      <nav class="tile flex items-center justify-between gap-3 px-4 py-3">
        <a class="flex items-center gap-2 font-bold text-ink" href="#">
          <span class="grid h-10 w-10 place-items-center rounded-lg bg-ink text-paper">
            <ArrowDownToLine class="h-5 w-5" />
          </span>
          <span class="hidden sm:inline">万能视频下载器</span>
        </a>
        <div class="hidden items-center gap-6 text-sm text-ink/70 md:flex">
          <a href="#platforms" class="hover:text-ink">支持平台</a>
          <a href="#ai" class="hover:text-ink">AI 功能</a>
          <a href="#plans" class="hover:text-ink">会员权益</a>
        </div>
        <div class="flex items-center gap-2">
          <button class="focus-ring hidden rounded-lg px-3 py-2 text-sm font-semibold text-ink/70 hover:bg-black/5 sm:inline-flex">
            登录
          </button>
          <button
            class="focus-ring inline-flex items-center gap-2 rounded-lg bg-coral px-3 py-2 text-sm font-bold text-white shadow-lift hover:bg-coral/90"
            @click="showPlans = true"
          >
            <Crown class="h-4 w-4" />
            开通会员
          </button>
        </div>
      </nav>
    </header>

    <section class="section-shell pb-10 pt-8 lg:pb-16 lg:pt-12">
      <div class="grid min-w-0 items-center gap-8 lg:grid-cols-[1.05fr_0.95fr]">
        <div class="min-w-0">
          <div class="mb-5 inline-flex max-w-full flex-wrap items-center gap-2 rounded-lg border border-ink/10 bg-white/70 px-3 py-2 text-sm font-semibold text-ink/70">
            <Sparkles class="h-4 w-4 shrink-0 text-coral" />
            <span class="min-w-0">由 yt-dlp 驱动，覆盖大量公开可访问的视频站点</span>
          </div>
          <h1 class="w-full max-w-4xl text-4xl font-black leading-tight text-ink sm:text-5xl lg:text-6xl">
            万能视频下载器
            <span class="block text-coral">复制链接，一键保存到本地</span>
          </h1>
          <p class="mt-5 w-full max-w-2xl text-base leading-8 text-ink/68 sm:text-lg">
            适合学习复盘、素材归档、公开课程离线保存。首版支持单链接解析下载，会员能力将扩展批量下载、视频总结和字幕翻译。
          </p>
        </div>

        <div class="tile min-w-0 p-4 sm:p-5">
          <div class="rounded-lg border border-dashed border-ink/15 bg-paper/70 p-3 text-sm font-semibold text-ink/65">
            请仅下载你拥有权利或平台允许保存的内容。
          </div>

          <div class="mt-4 flex flex-col gap-3 sm:flex-row">
            <label class="min-w-0 flex-1">
              <span class="sr-only">视频链接</span>
              <input
                v-model="videoUrl"
                class="focus-ring h-14 w-full rounded-lg border border-ink/12 bg-white px-4 text-base text-ink placeholder:text-ink/38"
                placeholder="粘贴公开视频链接，例如 https://..."
                @keyup.enter="handleProbe"
              />
            </label>
            <div class="grid grid-cols-2 gap-3 sm:flex">
              <button
                class="focus-ring inline-flex h-14 items-center justify-center gap-2 rounded-lg border border-ink/12 bg-white px-4 font-bold text-ink hover:bg-ink/5"
                @click="pasteFromClipboard"
              >
                <Search class="h-5 w-5" />
                粘贴
              </button>
              <button
                class="focus-ring inline-flex h-14 items-center justify-center gap-2 rounded-lg bg-ink px-5 font-bold text-paper shadow-glow hover:bg-coal disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="!canProbe"
                @click="handleProbe"
              >
                <Loader2 v-if="status === 'probing'" class="h-5 w-5 animate-spin" />
                <Play v-else class="h-5 w-5" />
                解析
              </button>
            </div>
          </div>

          <p class="mt-3 min-h-6 text-sm font-medium" :class="status === 'error' ? 'text-coral' : 'text-ink/58'">
            {{ message }}
          </p>

          <div v-if="probeResult" class="mt-5 grid gap-4 rounded-lg bg-white p-3 shadow-lift sm:grid-cols-[180px_1fr]">
            <div class="aspect-video overflow-hidden rounded-lg bg-ink/8">
              <img
                v-if="thumbnailUrl"
                :src="thumbnailUrl"
                alt="视频封面"
                class="h-full w-full object-cover"
              />
              <video
                v-else-if="previewVideoUrl"
                :src="previewVideoUrl"
                class="h-full w-full object-cover"
                muted
                autoplay
                loop
                playsinline
                preload="metadata"
              />
              <div v-else class="grid h-full place-items-center text-ink/45">
                <Play class="h-10 w-10" />
              </div>
            </div>
            <div class="min-w-0">
              <div class="mb-2 flex flex-wrap items-center gap-2 text-xs font-bold text-ink/55">
                <span class="rounded-lg bg-mint/20 px-2 py-1">{{ probeResult.extractor || "公开视频" }}</span>
                <span>{{ formatDuration(probeResult.duration) }}</span>
                <span v-if="probeResult.uploader">by {{ probeResult.uploader }}</span>
              </div>
              <h2 class="line-clamp-2 text-lg font-black text-ink">{{ probeResult.title }}</h2>
              <div class="mt-3 grid gap-3 sm:grid-cols-2">
                <select
                  v-model="selectedFormat"
                  class="focus-ring h-12 min-w-0 rounded-lg border border-ink/12 bg-paper px-3 text-sm font-semibold text-ink sm:col-span-2"
                >
                  <option v-for="format in probeResult.formats" :key="format.format_id" :value="format.format_id">
                    {{ format.label }} · {{ formatSize(format.filesize) }}
                  </option>
                </select>
                <button
                  class="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-coral px-5 font-black text-white hover:bg-coral/90"
                  :disabled="status === 'downloading'"
                  @click="handleDownload"
                >
                  <Loader2 v-if="status === 'downloading'" class="h-5 w-5 animate-spin" />
                  <ArrowDownToLine v-else class="h-5 w-5" />
                  下载
                </button>
                <button
                  class="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-ink px-5 font-black text-paper hover:bg-coal disabled:cursor-not-allowed disabled:opacity-55"
                  :disabled="aiStatus === 'analyzing'"
                  @click="handleAnalyze"
                >
                  <Loader2 v-if="aiStatus === 'analyzing'" class="h-5 w-5 animate-spin" />
                  <WandSparkles v-else class="h-5 w-5" />
                  AI 分析
                </button>
              </div>
            </div>
          </div>

          <Teleport defer to="#ai-analysis-slot">
          <div v-if="probeResult && aiStatus !== 'idle'" class="rounded-lg border border-ink/10 bg-white p-4 shadow-lift">
            <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <div class="inline-flex items-center gap-2 rounded-lg bg-grape/10 px-2.5 py-1 text-xs font-black text-grape">
                  <BrainCircuit class="h-4 w-4" />
                  AI 内容摘要
                </div>
                <p class="mt-2 text-sm font-medium" :class="aiStatus === 'error' ? 'text-coral' : 'text-ink/58'">
                  {{ aiMessage }}
                </p>
              </div>
              <button
                class="focus-ring inline-flex items-center justify-center gap-2 rounded-lg bg-coral px-4 py-3 text-sm font-black text-white hover:bg-coral/90 disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="aiStatus === 'analyzing'"
                @click="handleAnalyze"
              >
                <Loader2 v-if="aiStatus === 'analyzing'" class="h-4 w-4 animate-spin" />
                <WandSparkles v-else class="h-4 w-4" />
                {{ aiStatus === "analyzing" ? "生成中" : aiResult ? "重新分析" : "生成笔记" }}
              </button>
            </div>

            <div v-if="!aiResult && aiStatus === 'analyzing'" class="mt-4">
              <div class="flex gap-2 overflow-x-auto pb-2">
                <button class="focus-ring inline-flex shrink-0 items-center gap-2 rounded-lg bg-ink px-3 py-2 text-sm font-bold text-paper">
                  <BookOpen class="h-4 w-4" />
                  总结摘要
                </button>
                <button
                  v-for="tab in aiTabs.filter((item) => item.key !== 'summary')"
                  :key="tab.key"
                  class="inline-flex shrink-0 cursor-not-allowed items-center gap-2 rounded-lg bg-paper px-3 py-2 text-sm font-bold text-ink/35"
                  disabled
                >
                  <component :is="tab.icon" class="h-4 w-4" />
                  {{ tab.label }}
                </button>
              </div>
              <div class="mt-3 rounded-lg bg-paper p-4">
                <div v-if="summaryBlocks.length" class="markdown-body mt-3 min-h-24">
                  <template v-for="(block, index) in summaryBlocks" :key="`stream-md-${index}`">
                    <h2 v-if="block.type === 'heading' && block.level === 2">{{ block.text }}</h2>
                    <h3 v-else-if="block.type === 'heading'">{{ block.text }}</h3>
                    <blockquote v-else-if="block.type === 'quote'" v-html="block.html"></blockquote>
                    <pre v-else-if="block.type === 'code'"><code>{{ block.text }}</code></pre>
                    <ol v-else-if="block.type === 'list' && block.ordered" :start="block.start">
                      <li v-for="(item, itemIndex) in block.items" :key="`stream-li-o-${index}-${itemIndex}`" v-html="item"></li>
                    </ol>
                    <ul v-else-if="block.type === 'list'" :class="{ 'nested-list': block.nested }">
                      <li v-for="(item, itemIndex) in block.items" :key="`stream-li-${index}-${itemIndex}`" v-html="item"></li>
                    </ul>
                    <p v-else-if="block.type === 'paragraph'" v-html="block.html"></p>
                  </template>
                  <span class="ml-1 inline-block h-5 w-2 animate-pulse rounded-sm bg-coral align-middle"></span>
                </div>
                <p v-else class="mt-2 min-h-24 leading-8 text-ink/76">
                  AI 正在总结视频重点，内容会在这里实时出现...
                  <span class="ml-1 inline-block h-5 w-2 animate-pulse rounded-sm bg-coral align-middle"></span>
                </p>
              </div>
            </div>

            <div v-if="aiResult" class="mt-4">
              <div class="flex gap-2 overflow-x-auto pb-2">
                <button
                  v-for="tab in aiTabs"
                  :key="tab.key"
                  class="focus-ring inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-bold"
                  :class="aiActiveTab === tab.key ? 'bg-ink text-paper' : 'bg-paper text-ink/68 hover:bg-ink/5'"
                  @click="aiActiveTab = tab.key"
                >
                  <component :is="tab.icon" class="h-4 w-4" />
                  {{ tab.label }}
                </button>
              </div>

              <div v-if="aiActiveTab === 'summary'" class="mt-3 rounded-lg bg-paper p-4">
                <div>
                  <div class="markdown-body mt-3">
                    <template v-for="(block, index) in summaryBlocks" :key="`summary-md-${index}`">
                      <h2 v-if="block.type === 'heading' && block.level === 2">{{ block.text }}</h2>
                      <h3 v-else-if="block.type === 'heading'">{{ block.text }}</h3>
                      <blockquote v-else-if="block.type === 'quote'" v-html="block.html"></blockquote>
                      <pre v-else-if="block.type === 'code'"><code>{{ block.text }}</code></pre>
                      <ol v-else-if="block.type === 'list' && block.ordered" :start="block.start">
                        <li v-for="(item, itemIndex) in block.items" :key="`summary-li-o-${index}-${itemIndex}`" v-html="item"></li>
                      </ol>
                      <ul v-else-if="block.type === 'list'" :class="{ 'nested-list': block.nested }">
                        <li v-for="(item, itemIndex) in block.items" :key="`summary-li-${index}-${itemIndex}`" v-html="item"></li>
                      </ul>
                      <p v-else-if="block.type === 'paragraph'" v-html="block.html"></p>
                    </template>
                  </div>
                </div>
              </div>

              <div v-else-if="aiActiveTab === 'transcript'" class="mt-3">
                <div class="mb-3 flex flex-wrap justify-end gap-2">
                  <button class="focus-ring inline-flex items-center gap-2 rounded-lg bg-paper px-3 py-2 text-sm font-bold text-ink" @click="copyTranscript">
                    <ClipboardCopy class="h-4 w-4" />
                    复制全文
                  </button>
                  <div class="relative">
                    <button
                      class="focus-ring inline-flex items-center gap-2 rounded-lg bg-ink px-3 py-2 text-sm font-bold text-paper"
                      @click="showSubtitleMenu = !showSubtitleMenu"
                    >
                      <Download class="h-4 w-4" />
                      下载字幕
                      <ChevronDown class="h-4 w-4" />
                    </button>
                    <div v-if="showSubtitleMenu" class="absolute right-0 z-20 mt-2 w-44 overflow-hidden rounded-lg border border-ink/10 bg-white p-1 shadow-lift">
                      <button class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-bold text-ink hover:bg-paper" @click="downloadSubtitle('srt')">
                        <FileText class="h-4 w-4 text-coral" />
                        SRT 字幕
                      </button>
                      <button class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-bold text-ink hover:bg-paper" @click="downloadSubtitle('vtt')">
                        <FileText class="h-4 w-4 text-grape" />
                        VTT 字幕
                      </button>
                      <button class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-bold text-ink hover:bg-paper" @click="downloadSubtitle('txt')">
                        <FileText class="h-4 w-4 text-emerald-600" />
                        TXT 文本
                      </button>
                    </div>
                  </div>
                </div>
                <div class="max-h-80 overflow-y-auto rounded-lg bg-paper p-3">
                  <p
                    v-for="segment in aiResult.transcript_segments"
                    :key="`${segment.start}-${segment.text}`"
                    class="border-b border-ink/8 py-2 text-sm leading-6 text-ink/72 last:border-b-0"
                  >
                    <span class="mr-2 font-black text-coral">{{ formatTimestamp(segment.start) }}</span>
                    {{ segment.text }}
                  </p>
                </div>
              </div>

              <div v-else-if="aiActiveTab === 'mindmap'" class="mt-3 rounded-lg bg-paper p-4">
                <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 class="text-base font-black text-ink">图片思维导图</h3>
                    <p class="mt-1 text-sm font-medium text-ink/58">点击图片可全屏查看，下载会导出高清 PNG。</p>
                  </div>
                  <div class="flex flex-wrap gap-2">
                    <button class="focus-ring inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-bold text-ink shadow-lift" @click="showMindMapLightbox = true">
                      <Maximize2 class="h-4 w-4" />
                      全屏
                    </button>
                    <button class="focus-ring inline-flex items-center gap-2 rounded-lg bg-ink px-3 py-2 text-sm font-bold text-paper" @click="downloadMindMapPng">
                      <ImageDown class="h-4 w-4" />
                      下载高清图
                    </button>
                  </div>
                </div>
                <button
                  class="focus-ring block w-full overflow-hidden rounded-lg border border-ink/10 bg-white text-left shadow-lift"
                  @click="showMindMapLightbox = true"
                >
                  <img v-if="mindMapDataUrl" :src="mindMapDataUrl" alt="AI 生成的思维导图" class="h-auto w-full" />
                </button>
              </div>

              <div v-else class="mt-3">
                <div v-if="!aiChatHistory.length" class="rounded-lg border border-dashed border-ink/15 bg-paper p-5">
                  <div class="grid gap-4 md:grid-cols-[180px_1fr] md:items-center">
                    <div class="mx-auto grid h-36 w-36 place-items-center rounded-full bg-white shadow-lift">
                      <div class="grid h-24 w-24 place-items-center rounded-full bg-grape/10 text-grape">
                        <MessageCircle class="h-11 w-11" />
                      </div>
                    </div>
                    <div>
                      <h3 class="text-lg font-black text-ink">围绕视频内容继续追问</h3>
                      <p class="mt-2 leading-7 text-ink/62">
                        还没有发送消息。你可以从推荐问题开始，也可以直接输入自己关心的知识点、例子或复习问题。
                      </p>
                      <div class="mt-3 flex flex-wrap gap-2">
                        <button
                          v-for="question in chatQuestionOptions"
                          :key="`empty-chat-${question}`"
                          class="focus-ring rounded-lg bg-white px-3 py-2 text-left text-sm font-semibold text-ink/72 shadow-lift hover:text-ink"
                          @click="handleAskAi(question)"
                        >
                          {{ question }}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="grid gap-3">
                  <article v-for="item in aiChatHistory" :key="`${item.question}-${item.answer}`" class="rounded-lg bg-paper p-4">
                    <p class="text-sm font-black text-ink">问：{{ item.question }}</p>
                    <div class="mt-2 leading-7 text-ink/72">
                      <span class="font-black text-ink">答：</span>
                      <template v-if="item.answer">
                        <div class="markdown-body chat-markdown mt-2">
                          <template v-for="(block, index) in parseMarkdown(item.answer)" :key="`chat-md-${item.question}-${index}`">
                            <h2 v-if="block.type === 'heading' && block.level === 2">{{ block.text }}</h2>
                            <h3 v-else-if="block.type === 'heading'">{{ block.text }}</h3>
                            <blockquote v-else-if="block.type === 'quote'" v-html="block.html"></blockquote>
                            <pre v-else-if="block.type === 'code'"><code>{{ block.text }}</code></pre>
                            <ol v-else-if="block.type === 'list' && block.ordered" :start="block.start">
                              <li v-for="(listItem, itemIndex) in block.items" :key="`chat-li-o-${index}-${itemIndex}`" v-html="listItem"></li>
                            </ol>
                            <ul v-else-if="block.type === 'list'" :class="{ 'nested-list': block.nested }">
                              <li v-for="(listItem, itemIndex) in block.items" :key="`chat-li-${index}-${itemIndex}`" v-html="listItem"></li>
                            </ul>
                            <p v-else-if="block.type === 'paragraph'" v-html="block.html"></p>
                          </template>
                        </div>
                      </template>
                      <template v-else>
                        正在思考...
                        <span v-if="aiChatStatus === 'asking'" class="ml-1 inline-block h-4 w-2 animate-pulse rounded-sm bg-coral align-middle"></span>
                      </template>
                    </div>
                    <div v-if="item.related_segments.length" class="mt-3 flex flex-wrap gap-2">
                      <span v-for="segment in item.related_segments.slice(0, 4)" :key="`${item.question}-${segment.start}`" class="rounded-lg bg-white px-2 py-1 text-xs font-bold text-ink/55">
                        {{ formatTimestamp(segment.start) }}
                      </span>
                    </div>
                  </article>
                </div>
                <div class="mt-3 flex flex-col gap-2 sm:flex-row">
                  <input
                    v-model="aiQuestion"
                    class="focus-ring h-12 min-w-0 flex-1 rounded-lg border border-ink/12 bg-paper px-3 text-sm text-ink placeholder:text-ink/38"
                    placeholder="继续追问这个视频的内容..."
                    @keyup.enter="handleAskAi()"
                  />
                  <button
                    class="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-ink px-4 font-black text-paper hover:bg-coal disabled:cursor-not-allowed disabled:opacity-55"
                    :disabled="!aiQuestion.trim() || aiChatStatus === 'asking'"
                    @click="handleAskAi()"
                  >
                    <Loader2 v-if="aiChatStatus === 'asking'" class="h-4 w-4 animate-spin" />
                    <Send v-else class="h-4 w-4" />
                    发送
                  </button>
                </div>
              </div>
            </div>
          </div>
          </Teleport>
        </div>
      </div>
    </section>

    <section id="ai-analysis-slot" class="section-shell pb-12"></section>

    <section id="ai" class="section-shell pb-12">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <button
          v-for="action in advancedActions"
          :key="action.title"
          class="tile group flex min-h-32 flex-col items-start p-4 text-left transition hover:-translate-y-1 hover:shadow-glow"
          @click="handleAdvanced(action.path, action.title)"
        >
          <span class="mb-4 grid h-11 w-11 place-items-center rounded-lg bg-ink text-paper">
            <component :is="action.icon" class="h-5 w-5" />
          </span>
          <strong class="text-lg text-ink">{{ action.title }}</strong>
          <span class="mt-1 text-sm leading-6 text-ink/62">{{ action.desc }}</span>
          <span class="mt-auto inline-flex items-center gap-1 pt-3 text-sm font-bold text-coral">
            会员高级能力 <ChevronRight class="h-4 w-4 transition group-hover:translate-x-1" />
          </span>
        </button>
      </div>
    </section>

    <section id="platforms" class="section-shell pb-14">
      <div class="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <h2 class="text-2xl font-black text-ink sm:text-3xl">一个入口，覆盖更多下载场景</h2>
          <p class="mt-2 text-ink/62">首版先把单链接体验打磨顺滑，后续把高频能力逐步做成会员权益。</p>
        </div>
        <button class="focus-ring inline-flex items-center gap-2 rounded-lg bg-white px-4 py-3 text-sm font-bold text-ink shadow-lift" @click="showPlans = true">
          查看会员权益 <Crown class="h-4 w-4 text-coral" />
        </button>
      </div>

      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <article v-for="card in platformCards" :key="card.title" class="tile p-5">
          <span class="rounded-lg px-2.5 py-1 text-xs font-black" :class="card.tone">{{ card.tag }}</span>
          <h3 class="mt-4 text-xl font-black text-ink">{{ card.title }}</h3>
          <p class="mt-2 leading-7 text-ink/64">{{ card.desc }}</p>
        </article>
      </div>
    </section>

    <section id="plans" class="border-y border-ink/10 bg-ink py-12 text-paper">
      <div class="section-shell grid gap-8 lg:grid-cols-[0.82fr_1.18fr] lg:items-center">
        <div>
          <p class="text-sm font-black uppercase text-honey">会员转化预留</p>
          <h2 class="mt-3 text-3xl font-black sm:text-4xl">免费下载只是开始，高频使用需要更强能力</h2>
          <p class="mt-4 leading-8 text-paper/68">
            批量队列、AI 总结、字幕翻译、高清格式和团队协作会在后续阶段接入真实会员体系。
          </p>
        </div>
        <div class="grid gap-4 sm:grid-cols-3">
          <div v-for="plan in plans" :key="plan.id" class="rounded-lg border border-white/12 bg-white/8 p-4">
            <div class="flex items-center justify-between gap-2">
              <strong class="text-lg">{{ plan.name }}</strong>
              <span v-if="plan.badge" class="rounded-lg bg-honey px-2 py-1 text-xs font-black text-ink">{{ plan.badge }}</span>
            </div>
            <div class="mt-4 flex items-end gap-1">
              <span class="text-3xl font-black">{{ plan.price }}</span>
              <span class="pb-1 text-paper/55">/{{ plan.period }}</span>
            </div>
            <p class="mt-3 min-h-14 text-sm leading-6 text-paper/62">{{ plan.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <footer class="section-shell py-8 text-center text-sm text-ink/55">
      万能视频下载器 MVP · 请遵守平台规则和版权要求
    </footer>

    <div v-if="showPlans" class="fixed inset-0 z-50 grid place-items-center bg-ink/55 p-4 backdrop-blur-sm" @click.self="showPlans = false">
      <div class="max-h-[88vh] w-full max-w-5xl overflow-y-auto rounded-lg bg-paper p-4 shadow-glow sm:p-6">
        <div class="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 class="text-2xl font-black text-ink">选择适合你的下载方案</h2>
            <p class="mt-1 text-ink/62">首版展示会员路径，真实支付会在第二阶段接入。</p>
          </div>
          <button class="focus-ring rounded-lg bg-white px-3 py-2 font-bold text-ink shadow-lift" @click="showPlans = false">
            关闭
          </button>
        </div>

        <div class="grid gap-4 md:grid-cols-3">
          <article v-for="plan in plans" :key="plan.id" class="rounded-lg border border-ink/10 bg-white p-5 shadow-lift">
            <div class="flex items-center justify-between gap-2">
              <h3 class="text-xl font-black text-ink">{{ plan.name }}</h3>
              <span v-if="plan.badge" class="rounded-lg bg-coral px-2 py-1 text-xs font-black text-white">{{ plan.badge }}</span>
            </div>
            <div class="mt-4 flex items-end gap-1 text-ink">
              <span class="text-4xl font-black">{{ plan.price }}</span>
              <span class="pb-1 text-ink/55">/{{ plan.period }}</span>
            </div>
            <p class="mt-3 min-h-14 text-sm leading-6 text-ink/62">{{ plan.description }}</p>
            <ul class="mt-4 space-y-2">
              <li v-for="feature in plan.features" :key="feature.label" class="flex items-center gap-2 text-sm font-semibold text-ink/72">
                <Check class="h-4 w-4" :class="feature.highlighted ? 'text-coral' : 'text-emerald-600'" />
                {{ feature.label }}
              </li>
            </ul>
            <button class="focus-ring mt-5 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-ink px-4 py-3 font-black text-paper hover:bg-coal">
              <LockKeyhole v-if="plan.id !== 'free'" class="h-4 w-4" />
              <BadgeCheck v-else class="h-4 w-4" />
              {{ plan.cta }}
            </button>
          </article>
        </div>
      </div>
    </div>

    <div
      v-if="showMindMapLightbox"
      class="fixed inset-0 z-50 bg-ink/85 p-4 backdrop-blur-sm"
      @click.self="showMindMapLightbox = false"
    >
      <div class="mx-auto flex h-full max-w-7xl flex-col gap-3">
        <div class="flex items-center justify-between gap-3 text-paper">
          <div>
            <p class="text-sm font-black text-honey">AI 思维导图</p>
            <h2 class="line-clamp-1 text-xl font-black">{{ aiResult?.title }}</h2>
          </div>
          <div class="flex gap-2">
            <button class="focus-ring inline-flex items-center gap-2 rounded-lg bg-paper px-3 py-2 text-sm font-black text-ink" @click="downloadMindMapPng">
              <ImageDown class="h-4 w-4" />
              下载高清图
            </button>
            <button class="focus-ring grid h-10 w-10 place-items-center rounded-lg bg-white/10 text-paper hover:bg-white/15" @click="showMindMapLightbox = false">
              <X class="h-5 w-5" />
            </button>
          </div>
        </div>
        <div class="min-h-0 flex-1 rounded-lg bg-paper p-3">
          <img
            v-if="mindMapDataUrl"
            :src="mindMapDataUrl"
            alt="AI 生成的思维导图全屏预览"
            class="h-full w-full rounded-lg bg-white object-contain shadow-lift"
          />
        </div>
      </div>
    </div>

    <transition
      enter-active-class="transition duration-200"
      enter-from-class="translate-y-2 opacity-0"
      leave-active-class="transition duration-200"
      leave-to-class="translate-y-2 opacity-0"
    >
      <div v-if="showToast" class="fixed bottom-5 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 rounded-lg bg-ink px-4 py-3 text-center text-sm font-semibold text-paper shadow-glow">
        {{ toastText }}
      </div>
    </transition>
  </main>
</template>
