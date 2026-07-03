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

export interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
}

export interface EntitlementResponse {
  email: string;
  plan_id?: string | null;
  active: boolean;
  free_limit: number;
  free_used: number;
  free_remaining: number;
}

export interface AuthUser {
  id: number;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export interface TranscriptSegment {
  start: number;
  end?: number | null;
  text: string;
}

export interface AiOutlineItem {
  title: string;
  start?: number | null;
  summary: string;
}

export interface AiAnalysisResponse {
  analysis_id: string;
  title: string;
  source_url: string;
  summary: string;
  outline: AiOutlineItem[];
  key_points: string[];
  transcript_segments: TranscriptSegment[];
  suggested_questions: string[];
  model: string;
  created_at: string;
}

export interface AiChatResponse {
  answer: string;
  related_segments: TranscriptSegment[];
  model: string;
}

export interface AiChatMessage {
  question: string;
  answer: string;
  related_segments: TranscriptSegment[];
}

export type AiAnalysisStreamEvent =
  | { type: "status"; message: string; stage?: string; progress?: number }
  | { type: "transcript_ready"; title: string; transcript_count: number; transcript_segments: TranscriptSegment[] }
  | { type: "summary_delta"; delta: string }
  | { type: "complete"; analysis: AiAnalysisResponse }
  | { type: "error"; status_code?: number; message: string };

export type AiChatStreamEvent =
  | { type: "related_segments"; related_segments: TranscriptSegment[] }
  | { type: "answer_delta"; delta: string }
  | { type: "complete"; answer: string; related_segments: TranscriptSegment[]; model: string }
  | { type: "error"; status_code?: number; message: string };
