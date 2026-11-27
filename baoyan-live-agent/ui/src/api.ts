export type Audience = "students" | "parents" | "both";
export type Mode = "sample" | "live";
export type Kind = "promo" | "clip";
export type Status = "queued" | "running" | "review" | "completed" | "failed";
export type PromoOutput = "poster" | "video" | "copy";

export interface Config {
  live_promo: boolean;
  live_video: boolean;
  live_clip: boolean;
  sample_clip: boolean;
  max_upload_mb: number;
  max_source_minutes: number;
  team_access: boolean;
}

export interface TaskSummary {
  id: string;
  kind: Kind;
  status: Status;
  stage: string;
  title: string;
  audience: Audience;
  mode: Mode;
  created_at: string;
  updated_at: string;
}

export interface ClipForm {
  title: string;
  audience: Audience;
  instruction: string;
  seconds: number;
  mode: Mode;
}

export interface PromoForm {
  title: string;
  audience: Audience;
  brief: string;
  channel: string;
  scheduled_at: string;
  seconds: number;
  mode: Mode;
  outputs?: PromoOutput[];
}

export interface PromoPlan {
  headline: string;
  points: string[];
  narration: string;
  copy: string;
  image_prompt: string;
  video_prompt: string;
}

export interface Candidate {
  id: string;
  start: number;
  end: number;
  headline: string;
  reason: string;
  quote: string;
  copy: string;
  group_copy: string;
}

export interface ClipReview {
  candidate_id: string;
  start: number;
  end: number;
  headline: string;
  layout: "slides" | "speaker";
  copy: string;
  group_copy: string;
}

export interface Task extends Omit<TaskSummary, "title" | "audience" | "mode"> {
  action: "plan" | "render";
  asset_version?: string | null;
  error?: string;
  form: ClipForm | PromoForm;
  selection?: ClipReview | { plan: PromoPlan; scheduled_at: string } | null;
  plan?: PromoPlan;
  candidates?: Candidate[];
  duration?: number;
  outputs?: Record<string, string>;
  result?: { headline: string; copy: string; scheduled_at?: string; start?: number; end?: number; record: { actual_seconds: number | null } };
  calls?: Record<string, number>;
}

export const audienceLabels: Record<Audience, string> = {
  students: "大三学生", parents: "家长", both: "学生及家长",
};

export const statusLabels: Record<Status, string> = {
  queued: "等待处理", running: "处理中", review: "待审核", completed: "已完成", failed: "处理失败",
};

export function path(task: Task, file: string, download = false) {
  const options = new URLSearchParams();
  if (download) options.set("download", "true");
  if (task.asset_version && file !== "source.mp4") options.set("v", task.asset_version);
  return "/api/tasks/" + task.id + "/media/" + file + (options.size ? "?" + options : "");
}

export async function request<T>(path: string, body?: unknown): Promise<T> {
  const options: RequestInit = { cache: "no-store" };
  if (body !== undefined) {
    options.method = "POST";
    if (body instanceof FormData) {
      options.body = body;
    } else {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
  }
  const response = await fetch("/api" + path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "服务响应异常，请稍后重试。");
  }
  return response.json() as Promise<T>;
}

export function clock(seconds: number) {
  const rounded = Math.floor(seconds);
  return String(Math.floor(rounded / 60)).padStart(2, "0") + ":" + String(rounded % 60).padStart(2, "0");
}

export function apiError(error: unknown) {
  return error instanceof Error ? error.message : "工作台暂时不可用。";
}
