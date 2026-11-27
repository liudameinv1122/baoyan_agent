import { cloneElement, useId, useState, type FormEvent, type ReactElement } from "react";
import { ArrowRight, CalendarDays, Captions, Clapperboard, FileText, Image, Info, Upload, Video } from "lucide-react";
import { apiError, audienceLabels, request, type Audience, type ClipForm, type Config, type Kind, type Mode, type PromoForm, type PromoOutput, type Task } from "./api";

const SAMPLE: PromoForm = {
  title: "大三保研冲刺直播",
  audience: "students",
  brief: "用三个问题盘点课程成绩与科研经历\n规划寒假前的行动事项和时间节点\n直播集中答疑，整理材料准备清单",
  scheduled_at: "2026-12-05T19:00",
  channel: "视频号直播",
  seconds: 25,
  mode: "sample",
  outputs: ["poster", "video", "copy"],
};

const OUTPUT_OPTIONS: [PromoOutput, string][] = [["poster", "宣传海报"], ["video", "预热视频"], ["copy", "群文案"]];

type ControlAttributes = { id?: string; "aria-describedby"?: string };

export function Field({ label, children, hint }: { label: string; children: ReactElement<ControlAttributes>; hint?: string }) {
  const id = useId();
  return <div className="field"><label htmlFor={id}>{label}</label>
    {cloneElement(children, { id, "aria-describedby": hint ? id + "-hint" : undefined })}
    {hint && <small id={id + "-hint"}>{hint}</small>}
  </div>;
}

export function AudienceInput({ value, set, ...attributes }: { value: Audience; set: (value: Audience) => void } & ControlAttributes) {
  return <select {...attributes} value={value} onChange={event => set(event.target.value as Audience)}>
    {Object.entries(audienceLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
  </select>;
}

function ModeInput({ label, value, set, live }: { label: string; value: Mode; set: (value: Mode) => void; live?: boolean }) {
  return <Field label={label} hint={live ? "实时模式会调用后台配置的模型服务。" : "样例模式支持本地导出，实时生成由管理员配置。"}>
    <select value={value} onChange={event => set(event.target.value as Mode)}>
      <option value="sample">样例模式 · 本地处理</option>
      <option value="live" disabled={!live}>实时模式 · 调用 API</option>
    </select>
  </Field>;
}

function OutputGuide({ kind }: { kind: Kind }) {
  const promo = kind === "promo";
  const items = promo ? [[Image, "活动海报", "主题、直播时间与渠道"], [Video, "竖屏预热视频", "开场镜头、议题卡和活动卡"], [FileText, "群文案", "可复制或打包下载"]] as const
    : [[Clapperboard, "直播切片", "保留原声，裁切为竖屏"], [Captions, "字幕与封面", "成片 SRT 与 JPG 封面"], [FileText, "发布文案", "视频号配文与群文案"]] as const;
  return <aside className="panel output-guide">
    <h2>预计交付</h2>
    {items.map(([Icon, label, sub]) => <div className="guide-item" key={label}><span className="icon-box"><Icon size={19} /></span><div><strong>{label}</strong><p>{sub}</p></div></div>)}
    <div className="hint-box"><Info size={17} /><p>确认{promo ? "文案与分镜" : "选片和切点"}后，工作台才会导出成品。</p></div>
  </aside>;
}

function FormHeading({ kind }: { kind: Kind }) {
  return <div className="page-title">
    <a href="#/" className="back-link">‹ 工作台</a>
    <div className="eyebrow">{kind === "promo" ? "直播前" : "直播后"}</div>
    <h1>{kind === "promo" ? "制作直播预热" : "剪辑直播回放"}</h1>
    <p>{kind === "promo" ? "用一份活动简报制作海报、预热视频和群文案。" : "从直播录屏中找到适合目标受众的片段，选择后导出成片。"}</p>
  </div>;
}

function SubmitBar({ error, busy, label }: { error: string; busy: boolean; label: string }) {
  return <div className="form-footer">
    {error && <p className="error" role="alert">{error}</p>}
    <button className="button primary" disabled={busy}>{busy ? "正在提交…" : label}<ArrowRight size={17} /></button>
  </div>;
}

export function PromoCreate({ config, onCreate }: { config?: Config; onCreate: (task: Task) => void }) {
  const [form, setForm] = useState<PromoForm>({ ...SAMPLE, title: "", brief: "", scheduled_at: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const change = <K extends keyof PromoForm>(key: K, value: PromoForm[K]) => setForm(previous => ({ ...previous, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (form.mode === "live" && form.outputs?.includes("video") && !config?.live_video) {
      setError("实时视频尚未配置。请选择其他成品，或先用样例模式。"); return;
    }
    setBusy(true);
    try { onCreate(await request<Task>("/tasks/promo", form)); }
    catch (error) { setError(apiError(error)); }
    finally { setBusy(false); }
  }
  return <><FormHeading kind="promo" /><div className="form-layout">
    <form className="panel editor" onSubmit={submit}>
      <div className="panel-heading"><div><h2>活动简报</h2><p>使用北京时间填写活动安排。</p></div>
        <button type="button" className="button small" onClick={() => setForm(previous => ({ ...SAMPLE, mode: previous.mode }))}>填入样例简报</button></div>
      <Field label="活动名称"><input required maxLength={40} placeholder="例如：大三保研冲刺直播" value={form.title} onChange={event => change("title", event.target.value)} /></Field>
      <div className="two-fields">
        <Field label="目标受众"><AudienceInput value={form.audience} set={value => change("audience", value)} /></Field>
        <Field label="开播时间"><input required type="datetime-local" value={form.scheduled_at} onChange={event => change("scheduled_at", event.target.value)} /></Field>
      </div>
      <div className="two-fields">
        <Field label="观看渠道"><input required maxLength={30} value={form.channel} onChange={event => change("channel", event.target.value)} /></Field>
        <Field label="目标时长"><select value={form.seconds} onChange={event => change("seconds", Number(event.target.value))}>
          {[20, 25, 30].map(value => <option key={value} value={value}>{value} 秒</option>)}</select></Field>
      </div>
      <Field label="直播要点" hint="每行写一个议题，也可以粘贴活动讲稿。">
        <textarea rows={5} required minLength={5} maxLength={6000} placeholder="直播会讲什么？观众能带走什么？" value={form.brief} onChange={event => change("brief", event.target.value)} />
      </Field>
      <fieldset className="output-picker">
        <legend>成品类型</legend>
        {OUTPUT_OPTIONS.map(([value, label]) => {
          const selected = form.outputs ?? [];
          const checked = selected.includes(value);
          return <label key={value}><input type="checkbox" checked={checked} disabled={checked && selected.length === 1}
            onChange={() => change("outputs", checked ? selected.filter(item => item !== value) : [...selected, value])} />{label}</label>;
        })}
      </fieldset>
      <ModeInput label="制作模式" value={form.mode} set={value => change("mode", value)} live={config?.live_promo} />
      <SubmitBar busy={busy} error={error} label="生成预热方案" />
    </form><OutputGuide kind="promo" /></div></>;
}

export function ClipCreate({ config, onCreate }: { config?: Config; onCreate: (task: Task) => void }) {
  const [form, setForm] = useState<ClipForm>({ title: "", audience: "parents", instruction: "", seconds: 45, mode: "sample" });
  const [example, setExample] = useState(false);
  const [video, setVideo] = useState<File>();
  const [srt, setSrt] = useState<File>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const change = <K extends keyof ClipForm>(key: K, value: ClipForm[K]) => setForm(previous => ({ ...previous, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (!example && !video) { setError("请先添加 MP4 录屏。"); return; }
    if (!example && video && config && video.size > config.max_upload_mb * 1024 * 1024) { setError("录屏超过文件大小上限。"); return; }
    if (!example && !srt && form.mode === "sample") { setError("本地处理自有录屏时，请一并添加 SRT 字幕。"); return; }
    const body = new FormData();
    Object.entries(form).forEach(([key, value]) => body.set(key, String(value)));
    body.set("use_example", String(example));
    if (!example && video) body.set("video", video);
    if (!example && srt) body.set("srt", srt);
    setBusy(true);
    try { onCreate(await request<Task>("/tasks/clip", body)); }
    catch (error) { setError(apiError(error)); }
    finally { setBusy(false); }
  }
  return <><FormHeading kind="clip" /><div className="form-layout">
    <form className="panel editor" onSubmit={submit}>
      <div className="panel-heading"><div><h2>录屏与选片要求</h2><p>支持 MP4 录屏和 UTF-8 SRT 字幕。</p></div>
        {config?.sample_clip && <button type="button" className="button small" onClick={() => {
          setExample(true); setForm(previous => ({ ...previous, title: "大三保研冲刺｜行动与时间节点", audience: "parents", instruction: "重点剪家长需要关注的时间节点和提醒", mode: "sample", seconds: 45 }));
        }}>使用示例录屏</button>}</div>
      {example && <div className="hint-box"><Video size={18} /><p>已选中示例录屏和字幕</p><button type="button" className="text-button" onClick={() => setExample(false)}>更换</button></div>}
      {!example && <>
        <label className="upload" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); setVideo(event.dataTransfer.files[0]); }}>
          <input type="file" accept=".mp4,video/mp4" onChange={event => setVideo(event.target.files?.[0])} aria-label="选择 MP4 录屏" />
          <Upload size={25} /><strong>{video?.name || "选择或拖入 MP4 录屏"}</strong>
          <small>最长 {config?.max_source_minutes || 120} 分钟，最大 {config?.max_upload_mb || 512} MB</small>
        </label>
        <Field label="字幕文件" hint="实时模式可以从录屏音轨转写。本地处理需要已有字幕。">
          <input type="file" accept=".srt" onChange={event => setSrt(event.target.files?.[0])} />
        </Field>
      </>}
      <Field label="录屏主题"><input required maxLength={40} value={form.title} placeholder="输入直播或回放的主题" onChange={event => change("title", event.target.value)} /></Field>
      <div className="two-fields">
        <Field label="目标受众"><AudienceInput value={form.audience} set={value => change("audience", value)} /></Field>
        <Field label="最长成片时长（秒）"><input type="number" min={10} max={60} required value={form.seconds || ""} onChange={event => change("seconds", Number(event.target.value))} /></Field>
      </div>
      <Field label="选片要求"><textarea rows={3} maxLength={500} value={form.instruction} placeholder="例如：优先讲家长要帮忙确认的时间节点" onChange={event => change("instruction", event.target.value)} /></Field>
      <ModeInput label="制作模式" value={form.mode} set={value => change("mode", value)} live={config?.live_clip} />
      <SubmitBar busy={busy} error={error} label="生成候选片段" />
    </form><OutputGuide kind="clip" /></div></>;
}
