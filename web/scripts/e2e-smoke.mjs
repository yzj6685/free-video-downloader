const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:5174";

async function requestJson(path, options) {
  const response = await fetch(`${baseUrl}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function sampleDownload(url, headers = {}) {
  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`Download file failed: ${response.status}`);
  }
  if (!response.body) {
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength < 100) {
      throw new Error(`Downloaded too few bytes: ${buffer.byteLength}`);
    }
    return buffer.byteLength;
  }

  const reader = response.body.getReader();
  let bytes = 0;
  try {
    while (bytes < 2048) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
  if (bytes < 100) {
    throw new Error(`Downloaded too few bytes: ${bytes}`);
  }
  return bytes;
}

async function sampleThumbnail(thumbnail, sourceUrl) {
  if (!thumbnail) {
    throw new Error("Expected thumbnail URL");
  }
  const params = new URLSearchParams({ url: thumbnail, source_url: sourceUrl });
  return sampleDownload(`${baseUrl}/api/media/thumbnail?${params.toString()}`);
}

async function sampleVideoPreview(sourceUrl, formatId) {
  const params = new URLSearchParams({ url: sourceUrl, format_id: formatId });
  return sampleDownload(`${baseUrl}/api/media/video-preview?${params.toString()}`, {
    Range: "bytes=0-2047",
  });
}

const bilibiliUrl = "https://www.bilibili.com/video/BV1AQ4y1y7HC/";
const bilibiliProbe = await requestJson("/api/probe", {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8" },
  body: JSON.stringify({ url: bilibiliUrl }),
});

if (bilibiliProbe.extractor !== "BiliBiliFallback") {
  throw new Error(`Expected BiliBiliFallback, got ${bilibiliProbe.extractor}`);
}
if (!bilibiliProbe.formats?.some((format) => format.format_id === "bili-html5-16")) {
  throw new Error("Expected bili-html5-16 format");
}

const bilibiliDownload = await requestJson("/api/download", {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8" },
  body: JSON.stringify({
    url: bilibiliUrl,
    format_id: "bili-html5-16",
    delivery: "direct",
  }),
});

if (bilibiliDownload.type !== "proxy" || !bilibiliDownload.url?.startsWith("/api/download/file?")) {
  throw new Error(`Expected proxy download URL, got ${JSON.stringify(bilibiliDownload)}`);
}

const bilibiliBytes = await sampleDownload(`${baseUrl}${bilibiliDownload.url}`);
const bilibiliThumbnailBytes = await sampleThumbnail(bilibiliProbe.thumbnail, bilibiliUrl);

const douyinUrl = process.env.E2E_DOUYIN_URL || "https://v.douyin.com/R7kcLyG/";
const douyinProbe = await requestJson("/api/probe", {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8" },
  body: JSON.stringify({ url: douyinUrl }),
});

if (douyinProbe.extractor !== "DouyinResolver") {
  throw new Error(`Expected DouyinResolver, got ${douyinProbe.extractor}`);
}
if (!douyinProbe.formats?.some((format) => format.format_id?.startsWith("douyin-resolver-"))) {
  throw new Error("Expected at least one douyin-resolver format");
}
if (douyinProbe.formats.length < 1) {
  throw new Error(`Expected at least 1 Douyin format, got ${douyinProbe.formats.length}`);
}
if (!douyinProbe.formats.every((format) => Number.isFinite(format.filesize) && format.filesize > 100)) {
  throw new Error(`Expected Douyin formats to include filesize: ${JSON.stringify(douyinProbe.formats)}`);
}

const douyinDownload = await requestJson("/api/download", {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8" },
  body: JSON.stringify({
    url: douyinUrl,
    format_id: douyinProbe.recommended_format_id,
    delivery: "direct",
  }),
});

if (douyinDownload.type !== "proxy" || !douyinDownload.url?.startsWith("/api/download/file?")) {
  throw new Error(`Expected proxy Douyin download URL, got ${JSON.stringify(douyinDownload)}`);
}

const douyinBytes = await sampleDownload(`${baseUrl}${douyinDownload.url}`);
const douyinPreviewBytes = douyinProbe.thumbnail
  ? await sampleThumbnail(douyinProbe.thumbnail, douyinUrl)
  : await sampleVideoPreview(douyinUrl, douyinProbe.recommended_format_id);

console.log(
  JSON.stringify(
    {
      ok: true,
      bilibili: {
        title: bilibiliProbe.title,
        format: "bili-html5-16",
        downloadType: bilibiliDownload.type,
        sampledBytes: bilibiliBytes,
        thumbnailBytes: bilibiliThumbnailBytes,
      },
      douyin: {
        title: douyinProbe.title,
        format: douyinProbe.recommended_format_id,
        formatCount: douyinProbe.formats.length,
        downloadType: douyinDownload.type,
        sampledBytes: douyinBytes,
        previewBytes: douyinPreviewBytes,
      },
    },
    null,
    2,
  ),
);
