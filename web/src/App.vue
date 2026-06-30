<script setup lang="ts">
import {
  ArrowDownToLine,
  BadgeCheck,
  BookOpen,
  BrainCircuit,
  Captions,
  Check,
  ChevronRight,
  ClipboardCopy,
  Crown,
  Languages,
  Loader2,
  MessageCircle,
  LockKeyhole,
  Play,
  Search,
  Send,
  Sparkles,
  WandSparkles,
  Zap,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { analyzeVideoStream, chatWithVideo, fetchPlans, probeVideo, requestComingSoon, startDownload } from "./api";
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
const aiMessage = ref("解析视频后，可提取平台字幕并生成 AI 学习笔记。");
const aiResult = ref<AiAnalysisResponse | null>(null);
const aiStreamingSummary = ref("");
const aiActiveTab = ref<"summary" | "transcript" | "mindmap" | "chat">("summary");
const aiQuestion = ref("");
const aiChatStatus = ref<"idle" | "asking">("idle");
const aiChatHistory = ref<AiChatMessage[]>([]);

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
    aiMessage.value = "解析成功后，可继续生成 AI 学习笔记。";
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
    showNotice("请先解析一个视频，再生成 AI 学习笔记。");
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
        aiMessage.value = "AI 学习笔记已生成，可继续追问视频内容。";
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
    aiMessage.value = "AI 学习笔记已生成，可继续追问视频内容。";
  } catch (error) {
    aiStatus.value = "error";
    aiMessage.value = error instanceof Error ? error.message : "AI 分析失败，请稍后重试。";
  }
}

async function handleAskAi(question?: string) {
  const finalQuestion = (question || aiQuestion.value).trim();
  if (!aiResult.value || !finalQuestion || aiChatStatus.value === "asking") return;

  aiChatStatus.value = "asking";
  try {
    const result = await chatWithVideo(aiResult.value.analysis_id, finalQuestion);
    aiChatHistory.value.push({
      question: finalQuestion,
      answer: result.answer,
      related_segments: result.related_segments,
    });
    aiQuestion.value = "";
  } catch (error) {
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
                  AI 学习笔记
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
                <h3 class="text-base font-black text-ink">视频总结</h3>
                <p class="mt-2 min-h-24 whitespace-pre-wrap leading-8 text-ink/76">
                  {{ aiStreamingSummary || "正在读取字幕并连接 DeepSeek，摘要会在这里实时出现..." }}
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
                <div class="space-y-5">
                  <section>
                    <h3 class="text-base font-black text-ink">视频总结</h3>
                    <p class="mt-2 leading-8 text-ink/76">{{ aiResult.summary }}</p>
                  </section>

                  <section v-if="aiResult.key_points.length">
                    <h3 class="text-base font-black text-ink">核心知识点</h3>
                    <ul class="mt-2 grid gap-2 sm:grid-cols-2">
                      <li v-for="point in aiResult.key_points" :key="point" class="flex gap-2 rounded-lg bg-white p-3 text-sm font-semibold leading-6 text-ink/76 shadow-lift">
                        <Check class="mt-1 h-4 w-4 shrink-0 text-emerald-600" />
                        <span>{{ point }}</span>
                      </li>
                    </ul>
                  </section>

                  <section v-if="aiResult.outline.length">
                    <h3 class="text-base font-black text-ink">章节大纲</h3>
                    <div class="mt-2 grid gap-2">
                      <article v-for="item in aiResult.outline" :key="`${item.start}-${item.title}`" class="rounded-lg bg-white p-3 shadow-lift">
                        <div class="flex flex-wrap items-center gap-2">
                          <span v-if="item.start !== null && item.start !== undefined" class="rounded-lg bg-paper px-2 py-1 text-xs font-black text-coral">
                            {{ formatTimestamp(item.start) }}
                          </span>
                          <h4 class="text-sm font-black text-ink">{{ item.title }}</h4>
                        </div>
                        <p class="mt-1 text-sm leading-6 text-ink/64">{{ item.summary }}</p>
                      </article>
                    </div>
                  </section>
                </div>
                <div v-if="aiResult.suggested_questions.length" class="mt-4 flex flex-wrap gap-2">
                  <button
                    v-for="question in aiResult.suggested_questions"
                    :key="question"
                    class="focus-ring rounded-lg bg-white px-3 py-2 text-left text-sm font-semibold text-ink/72 shadow-lift hover:text-ink"
                    @click="aiActiveTab = 'chat'; handleAskAi(question)"
                  >
                    {{ question }}
                  </button>
                </div>
              </div>

              <div v-else-if="aiActiveTab === 'transcript'" class="mt-3">
                <div class="mb-3 flex justify-end">
                  <button class="focus-ring inline-flex items-center gap-2 rounded-lg bg-paper px-3 py-2 text-sm font-bold text-ink" @click="copyTranscript">
                    <ClipboardCopy class="h-4 w-4" />
                    复制全文
                  </button>
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
                <div class="relative grid gap-3">
                  <div class="rounded-lg border border-grape/20 bg-white p-4 shadow-lift">
                    <div class="inline-flex items-center gap-2 rounded-lg bg-grape/10 px-2.5 py-1 text-xs font-black text-grape">
                      <BrainCircuit class="h-4 w-4" />
                      中心主题
                    </div>
                    <p class="mt-2 text-lg font-black text-ink">{{ aiResult.title }}</p>
                  </div>
                  <div class="grid gap-3 md:grid-cols-2">
                    <article v-for="item in aiResult.outline" :key="`mind-${item.start}-${item.title}`" class="rounded-lg border border-ink/8 bg-white p-4 shadow-lift">
                      <div class="flex items-center gap-2">
                        <span v-if="item.start !== null && item.start !== undefined" class="rounded-lg bg-coral/10 px-2 py-1 text-xs font-black text-coral">
                          {{ formatTimestamp(item.start) }}
                        </span>
                        <h3 class="text-sm font-black text-ink">{{ item.title }}</h3>
                      </div>
                      <p class="mt-2 text-sm leading-6 text-ink/62">{{ item.summary }}</p>
                    </article>
                  </div>
                  <div v-if="aiResult.key_points.length" class="rounded-lg border border-emerald-600/15 bg-white p-4 shadow-lift">
                    <h3 class="text-sm font-black text-ink">关键结论</h3>
                    <div class="mt-2 flex flex-wrap gap-2">
                      <span v-for="point in aiResult.key_points" :key="`map-${point}`" class="rounded-lg bg-mint/18 px-3 py-2 text-xs font-bold leading-5 text-emerald-800">
                        {{ point }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else class="mt-3">
                <div class="grid gap-3">
                  <article v-for="item in aiChatHistory" :key="`${item.question}-${item.answer}`" class="rounded-lg bg-paper p-4">
                    <p class="text-sm font-black text-ink">问：{{ item.question }}</p>
                    <p class="mt-2 leading-7 text-ink/72">答：{{ item.answer }}</p>
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
