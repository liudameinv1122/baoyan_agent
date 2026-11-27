import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowDownToLine, ArrowLeft, ArrowRight, AlertCircle, Check, ChevronDown, Clock3, Copy, Download, FileText, Film, Image, LoaderCircle, Pencil, Play, Plus, RefreshCw, Scissors, Trash2 } from "lucide-react";
import { apiError, audienceLabels, clock, path, request, statusLabels, type Candidate, type ClipForm, type ClipReview, type PromoForm, type PromoPlan, type Task } from "./api";
import { AudienceInput, Field } from "./forms";

export function StatusPill({ status }: { status: Task["status"] }) {
  return <span className={"status-pill " + status}><span />{statusLabels[status]}</span>;
}

function submitEndpoint(task: Task, endpoint: string, body: unknown) {
  return request<Task>("/tasks/" + task.id + "/" + endpoint, body);
}

function ErrorText({ text }: { text: string }) {
  return text ? <p className="error" role="alert"><AlertCircle size={17} />{text}</p> : null;
}

function PromoEditor({ task, update }: { task: Task; update: (task: Task) => void }) {
  const previous = task.selection && "plan" in task.selection ? task.selection : undefined;
  const form = task.form as PromoForm;
  const needs = form.outputs ?? ["poster", "video", "copy"];
  const [plan, setPlan] = useState<PromoPlan>(previous?.plan ?? task.plan!);
  const [date, setDate] = useState((previous?.scheduled_at ?? form.scheduled_at).slice(0, 16));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const change = <K extends keyof PromoPlan>(key: K, value: PromoPlan[K]) => setPlan(previous => ({ ...previous, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { update(await submitEndpoint(task, "promo-review", { scheduled_at: date, plan })); }
    catch (error) { setError(apiError(error)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="review-layout">
    <div className="panel editor">
      <div className="panel-heading"><div><h2>确认预热方案</h2><p>确认开播时间、海报标题和视频议题后导出。</p></div></div>
      <div className="two-fields">
        <Field label="海报标题"><input required maxLength={40} value={plan.headline} onChange={event => change("headline", event.target.value)} /></Field>
        <Field label="开播时间"><input required type="datetime-local" value={date} onChange={event => setDate(event.target.value)} /></Field>
      </div>
      <div className="field"><span>预热视频议题</span>
        {plan.points.map((point, index) => <div className="point-row" key={index}>
          <input required minLength={2} maxLength={95} aria-label={"议题 " + (index + 1)} value={point}
            onChange={event => change("points", plan.points.map((value, i) => i === index ? event.target.value : value))} />
          {plan.points.length > 2 && <button className="button square" type="button" aria-label={"移除议题 " + (index + 1)}
            onClick={() => change("points", plan.points.filter((_, i) => i !== index))}><Trash2 size={16} /></button>}
        </div>)}
        {plan.points.length < 3 && <button className="button small self-start" type="button" onClick={() => change("points", [...plan.points, ""])}><Plus size={15} />增加议题</button>}
      </div>
      {form.mode === "live" && needs.includes("video") && <Field label="旁白"><textarea rows={3} required minLength={5} maxLength={300} value={plan.narration}
        onChange={event => change("narration", event.target.value)} /></Field>}
      {needs.includes("copy") && <Field label="群文案" hint="导出时会自动附带活动时间和观看渠道。"><textarea required minLength={2} maxLength={1200} rows={4} value={plan.copy}
        onChange={event => change("copy", event.target.value)} /></Field>}
      {form.mode === "live" && (needs.includes("video") || needs.includes("poster")) && <details className="disclosure">
        <summary>查看和修改生成素材的提示词<ChevronDown size={17} /></summary>
        <Field label="海报背景"><textarea rows={3} minLength={5} maxLength={900} required value={plan.image_prompt} onChange={event => change("image_prompt", event.target.value)} /></Field>
        {needs.includes("video") && <Field label="开场镜头"><textarea rows={3} minLength={5} maxLength={900} required value={plan.video_prompt} onChange={event => change("video_prompt", event.target.value)} /></Field>}
      </details>}
      <ErrorText text={error} />
      <div className="form-footer">
        {form.mode === "live" && (needs.includes("poster") || needs.includes("video")) && <p className="muted">提交后会按需调用素材生成服务。</p>}
        <button className="button primary" disabled={busy}>{busy ? "正在提交…" : "确认并导出"}<ArrowRight size={17} /></button>
      </div>
    </div>
    <aside className="panel output-guide">
      <h2>{needs.includes("video") ? "视频分镜" : "活动信息"}</h2>
      {needs.includes("video") && <>
      <div className="guide-item"><span className="icon-box"><Film size={19} /></span><div><strong>开场镜头</strong><p>约 4 秒</p></div></div>
      <div className="guide-item"><span className="icon-box"><FileText size={19} /></span><div><strong>{plan.points.length} 张议题卡</strong><p>呈现直播能讲清楚的重点</p></div></div>
      </>}
      <div className="guide-item"><span className="icon-box"><Clock3 size={19} /></span><div><strong>{needs.includes("video") ? "活动片尾" : "开播时间"}</strong><p>{date.replace("T", " ")} · {form.channel}</p></div></div>
      {needs.includes("video") && <div className="hint-box"><p>{form.mode === "live" ? "修改开播时间会复用已生成的背景和镜头。" : "开场使用示例镜头，议题卡和活动卡按你审核的内容渲染。"}</p></div>}
    </aside>
  </form>;
}

function configuredCut(candidate: Candidate, layout: ClipReview["layout"]): ClipReview {
  return { candidate_id: candidate.id, start: candidate.start, end: candidate.end, layout,
    headline: candidate.headline, copy: candidate.copy, group_copy: candidate.group_copy };
}

function ClipEditor({ task, update }: { task: Task; update: (task: Task) => void }) {
  const form = task.form as ClipForm;
  const candidates = task.candidates!;
  const previous = task.selection && "candidate_id" in task.selection ? task.selection : undefined;
  const [cut, setCut] = useState<ClipReview>(previous ?? configuredCut(candidates[0], "slides"));
  const [replan, setReplan] = useState({ audience: form.audience, instruction: form.instruction, seconds: form.seconds });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const previewing = useRef(false);
  const change = <K extends keyof ClipReview>(key: K, value: ClipReview[K]) => setCut(previous => ({ ...previous, [key]: value }));
  const selected = candidates.find(item => item.id === cut.candidate_id)!;
  function seek(start: number, play = false) {
    if (!video.current) return;
    previewing.current = play;
    video.current.currentTime = start;
    if (play) void video.current.play().catch(() => { previewing.current = false; });
    else video.current.pause();
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (!Number.isFinite(cut.start) || !Number.isFinite(cut.end) || cut.end - cut.start < 0.5 ||
        cut.end - cut.start > form.seconds + 0.001 || cut.end > (task.duration ?? 0) + 0.0005) {
      setError("请将起止时间设在原片内，且片段时长不超过 " + form.seconds + " 秒。");
      return;
    }
    setBusy(true);
    try { update(await submitEndpoint(task, "clip-review", cut)); }
    catch (error) { setError(apiError(error)); }
    finally { setBusy(false); }
  }
  async function rerank(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { update(await submitEndpoint(task, "replan", replan)); }
    catch (error) { setError(apiError(error)); }
    finally { setBusy(false); }
  }
  return <div className="clip-workspace">
    <section className="panel raw-media">
      <div className="panel-heading"><div><h2>原片与候选片段</h2><p>点击条目跳到原片对应位置。</p></div></div>
      <video ref={video} controls playsInline preload="metadata" className="source-video" src={path(task, "source.mp4")} onTimeUpdate={() => {
        if (previewing.current && video.current && video.current.currentTime >= cut.end) {
          video.current.pause(); previewing.current = false;
        }
      }} />
      <div className="candidate-list">
        {candidates.map(candidate => <button className={"candidate " + (candidate.id === cut.candidate_id ? "selected" : "")}
          type="button" key={candidate.id} aria-pressed={candidate.id === cut.candidate_id} onClick={() => {
            setCut(configuredCut(candidate, cut.layout)); seek(candidate.start);
          }}>
          <span><strong>{candidate.headline}</strong><small>{candidate.reason}</small></span>
          <time>{clock(candidate.start)}–{clock(candidate.end)}</time>
        </button>)}
      </div>
      <div className="source-quote"><span>原片字幕</span><p>{selected.quote}</p></div>
      <details className="disclosure">
        <summary>调整受众或选片要求<ChevronDown size={17} /></summary>
        <form className="subform" onSubmit={rerank}>
          <Field label="目标受众"><AudienceInput value={replan.audience} set={audience => setReplan({ ...replan, audience })} /></Field>
          <Field label="最长成片时长（秒）"><input required min={10} max={60} type="number" value={replan.seconds || ""} onChange={event => setReplan({ ...replan, seconds: Number(event.target.value) })} /></Field>
          <Field label="选片要求"><textarea rows={2} maxLength={500} value={replan.instruction} onChange={event => setReplan({ ...replan, instruction: event.target.value })} /></Field>
          <button className="button small self-start" disabled={busy}><RefreshCw size={15} />重新选片</button>
        </form>
      </details>
    </section>
    <form className="panel editor" onSubmit={submit}>
      <div className="panel-heading"><div><h2>编辑成片</h2><p>调整切点，确认封面标题和渠道文案。</p></div></div>
      <Field label="封面标题"><input required minLength={2} maxLength={40} value={cut.headline} onChange={event => change("headline", event.target.value)} /></Field>
      <div className="two-fields">
        <Field label="起点（秒）"><input required type="number" min={0} step={0.001} value={Number.isNaN(cut.start) ? "" : cut.start}
          onChange={event => change("start", event.target.valueAsNumber)} /></Field>
        <Field label="终点（秒）"><input required type="number" min={0.5} step={0.001} value={Number.isNaN(cut.end) ? "" : cut.end}
          onChange={event => change("end", event.target.valueAsNumber)} /></Field>
      </div>
      <button className="button small self-start" type="button" disabled={!(cut.start >= 0 && cut.end > cut.start)}
        onClick={() => seek(cut.start, true)}><Play size={16} />预览选段</button>
      <Field label="画面布局"><select value={cut.layout} onChange={event => change("layout", event.target.value as ClipReview["layout"])}>
        <option value="slides">保留完整 PPT 或录屏</option><option value="speaker">裁切为居中讲师画面</option></select></Field>
      <Field label="视频号配文"><textarea required minLength={2} maxLength={1200} rows={3} value={cut.copy} onChange={event => change("copy", event.target.value)} /></Field>
      <Field label="群文案"><textarea required minLength={2} maxLength={1200} rows={3} value={cut.group_copy} onChange={event => change("group_copy", event.target.value)} /></Field>
      <ErrorText text={error} />
      <div className="form-footer"><button className="button primary" disabled={busy}>{busy ? "正在提交…" : "确认并导出"}<Scissors size={17} /></button></div>
    </form>
  </div>;
}

function Completed({ task, edit }: { task: Task; edit: () => void }) {
  const [copy, setCopy] = useState("");
  const promo = task.kind === "promo";
  const filename = promo ? "preview.mp4" : "clip.mp4";
  const image = promo ? "poster.jpg" : "cover.jpg";
  const result = task.result!;
  const hasVideo = !!task.outputs?.[filename];
  const hasImage = !!task.outputs?.[image];
  return <div className="complete-layout">
    <section className="panel completion-media">
      <div className="panel-heading"><div><h2>成品预览</h2>{result.record.actual_seconds !== null && <p>竖屏 MP4 · {result.record.actual_seconds.toFixed(1)} 秒</p>}</div><button className="button small" onClick={edit}><Pencil size={16} />继续编辑</button></div>
      <div className="asset-previews">
        {hasVideo && <figure><video controls playsInline preload="metadata" src={path(task, filename)} poster={hasImage ? path(task, image) : undefined} /><figcaption>{promo ? "预热视频" : "直播切片"}</figcaption></figure>}
        {hasImage && <figure><img src={path(task, image)} alt={promo ? "活动海报" : "短视频封面"} /><figcaption>{promo ? "活动海报" : "短视频封面"}</figcaption></figure>}
      </div>
      {!hasVideo && !hasImage && <p className="copy-text">{result.copy}</p>}
    </section>
    <aside className="panel output-guide completed-guide">
      <div className="panel-heading"><div><h2>下载成品</h2><p>含实际导出的成片与制作记录。</p></div></div>
      <a className="button primary" href={path(task, "materials.zip", true)}><Download size={17} />下载整包</a>
      <div className="downloads">
        {Object.entries(task.outputs ?? {}).map(([file, label]) => <a key={file} href={path(task, file, true)}>
          {file.endsWith(".mp4") ? <Film size={17} /> : file.endsWith(".jpg") ? <Image size={17} /> : <FileText size={17} />}
          {label}<ArrowDownToLine size={15} /></a>)}
      </div>
      {!!result.copy && <div className="copy-box"><div><h3>发布文案</h3><button className="button small" onClick={async () => {
        try { await navigator.clipboard.writeText(result.copy); setCopy("已复制"); }
        catch { setCopy("请直接选中文案，或下载文案文件"); }
      }}><Copy size={15} />复制</button></div><p className="copy-text">{result.copy}</p><small role="status">{copy}</small></div>}
      {!!Object.keys(task.calls ?? {}).length && <details className="disclosure"><summary>API 调用记录<ChevronDown size={17} /></summary>
        {Object.entries(task.calls!).map(([name, count]) => <p className="muted" key={name}>{name} · {count} 次请求</p>)}</details>}
    </aside>
  </div>;
}

export function TaskScreen({ id }: { id: string }) {
  const [task, setTask] = useState<Task>();
  const [network, setNetwork] = useState("");
  const [editing, setEditing] = useState(false);
  const [retrying, setRetrying] = useState(false);
  useEffect(() => {
    let active = true;
    let loading = false;
    async function load() {
      if (loading) return;
      loading = true;
      try {
        const data = await request<Task>("/tasks/" + id);
        if (active) {
          setTask(current => !current || data.updated_at >= current.updated_at ? data : current);
          setNetwork("");
        }
      } catch (error) { if (active) setNetwork(apiError(error)); }
      finally { loading = false; }
    }
    void load();
    const timer = window.setInterval(() => { void load(); }, 1300);
    return () => { active = false; window.clearInterval(timer); };
  }, [id]);
  function update(task: Task) {
    setEditing(false); setTask(task); setNetwork("");
  }
  if (!task) return <div className="panel centered"><ErrorText text={network} />{!network && <><LoaderCircle className="spinner" /><p>正在读取任务</p></>}<a className="button small" href="#/history"><ArrowLeft size={16} />任务记录</a></div>;
  const canEdit = task.kind === "promo" ? !!task.plan : !!task.candidates?.length;
  const running = task.status === "queued" || task.status === "running";
  return <>
    <div className="page-title task-title">
      <a href="#/history" className="back-link">‹ 任务记录</a>
      <div className="eyebrow">{task.kind === "promo" ? "直播预热" : "直播回放"}</div>
      <div className="title-line"><h1>{task.form.title}</h1><StatusPill status={task.status} /></div>
      <p>{audienceLabels[task.form.audience]} · {task.form.seconds} 秒{task.kind === "clip" ? "以内" : ""} · {task.form.mode === "sample" ? "样例模式" : "实时模式"}</p>
    </div>
    <ErrorText text={network} />
    {running && <div className="panel centered progress" role="status"><span className="progress-icon"><LoaderCircle className="spinner" size={27} /></span>
      <h2>{task.stage}</h2><p>任务会在后台继续处理，你可以从任务记录回到此处。</p><a className="button small" href="#/history">查看任务记录</a></div>}
    {task.status === "failed" && <div className="panel failure">
      <ErrorText text={task.error || "这次处理失败。"} />
      <div className="actions"><button className="button primary" disabled={retrying} onClick={async () => {
        setRetrying(true);
        try { update(await submitEndpoint(task, "retry", {})); }
        catch (error) { setNetwork(apiError(error)); }
        finally { setRetrying(false); }
      }}><RefreshCw size={16} />重试当前步骤</button>
        {canEdit && <button className="button" onClick={() => setEditing(true)}><Pencil size={16} />调整方案</button>}
        {!canEdit && <a className="button" href={task.kind === "promo" ? "#/promo" : "#/clip"}>新建任务</a>}
      </div>
    </div>}
    {task.status === "completed" && !editing && <Completed task={task} edit={() => setEditing(true)} />}
    {task.status === "completed" && editing && <div className="editing-banner"><Check size={16} />已有成品可继续下载<a href={path(task, "materials.zip", true)}>下载上一版</a></div>}
    {(task.status === "review" || (editing && !running)) && canEdit && (task.kind === "promo"
      ? <PromoEditor key={task.id + task.status} task={task} update={update} />
      : <ClipEditor key={task.id + task.status} task={task} update={update} />)}
  </>;
}
