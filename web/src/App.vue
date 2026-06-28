<script setup lang="ts">
import {
  ArrowDownToLine,
  BadgeCheck,
  Captions,
  Check,
  ChevronRight,
  Crown,
  Languages,
  Loader2,
  LockKeyhole,
  Play,
  Search,
  Sparkles,
  WandSparkles,
  Zap,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { fetchPlans, probeVideo, requestComingSoon, startDownload } from "./api";
import type { BillingPlan, ProbeResponse } from "./types";

const videoUrl = ref("");
const selectedFormat = ref("best");
const probeResult = ref<ProbeResponse | null>(null);
const status = ref<"idle" | "probing" | "ready" | "downloading" | "error">("idle");
const message = ref("支持公开视频链接，粘贴后即可解析。");
const plans = ref<BillingPlan[]>([]);
const showPlans = ref(false);
const showToast = ref(false);
const toastText = ref("");

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

async function handleAdvanced(path: string, title: string) {
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
      <div class="grid items-center gap-8 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <div class="mb-5 inline-flex items-center gap-2 rounded-lg border border-ink/10 bg-white/70 px-3 py-2 text-sm font-semibold text-ink/70">
            <Sparkles class="h-4 w-4 text-coral" />
            由 yt-dlp 驱动，覆盖大量公开可访问的视频站点
          </div>
          <h1 class="max-w-4xl text-4xl font-black leading-tight text-ink sm:text-5xl lg:text-6xl">
            万能视频下载器
            <span class="block text-coral">复制链接，一键保存到本地</span>
          </h1>
          <p class="mt-5 max-w-2xl text-base leading-8 text-ink/68 sm:text-lg">
            适合学习复盘、素材归档、公开课程离线保存。首版支持单链接解析下载，会员能力将扩展批量下载、视频总结和字幕翻译。
          </p>
        </div>

        <div class="tile p-4 sm:p-5">
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
              <div class="mt-3 flex flex-col gap-3 sm:flex-row">
                <select
                  v-model="selectedFormat"
                  class="focus-ring h-12 min-w-0 flex-1 rounded-lg border border-ink/12 bg-paper px-3 text-sm font-semibold text-ink"
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
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

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
