export interface VideoFormat {
  format_id: string;
  label: string;
  extension?: string | null;
  resolution?: string | null;
  filesize?: number | null;
  has_video: boolean;
  has_audio: boolean;
}

export interface ProbeResponse {
  title: string;
  url: string;
  extractor?: string | null;
  uploader?: string | null;
  duration?: number | null;
  thumbnail?: string | null;
  formats: VideoFormat[];
  recommended_format_id: string;
  may_require_proxy: boolean;
}

export interface BillingPlan {
  id: string;
  name: string;
  price: string;
  period: string;
  badge?: string | null;
  description: string;
  cta: string;
  features: Array<{ label: string; highlighted: boolean }>;
}

export interface ComingSoonResponse {
  status: "coming_soon";
  feature: string;
  message: string;
}
