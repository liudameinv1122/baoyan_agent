import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { ArrowDownRight, ArrowRight, ArrowUpRight, CircleHelp, Clapperboard, Clock3, Film, History, LayoutGrid, Plus, Search, Sparkles, X } from "lucide-react";
import { apiError, audienceLabels, request, statusLabels, type Config, type Kind, type Status, type Task, type TaskSummary } from "./api";
import { ClipCreate, PromoCreate } from "./forms";
import { StatusPill, TaskScreen } from "./detail";
import "./styles.css";

type Page = "home" | "history" | "promo" | "clip" | "task";
type Route = { page: Page; id?: string };

function route(): Route {
  const parts = window.location.hash.slice(1).split("/").filter(Boolean);
  if (["history", "promo", "clip"].includes(parts[0])) return { page: parts[0] as Page };
  if (parts[0] === "task" && /^[a-f0-9-]{36}$/.test(parts[1] ?? "")) return { page: "task", id: parts[1] };
  return { page: "home" };
}

const LINKS = [
  ["home", "#/", "工作台", LayoutGrid],
  ["history", "#/history", "任务记录", History],
  ["promo", "#/promo", "制作预热", Sparkles],
  ["clip", "#/clip", "剪辑回放", Clapperboard],
] as const;

const PAGE_NAMES: Record<Page, string> = { home: "工作台", history: "任务记录", promo: "制作预热", clip: "剪辑回放", task: "任务详情" };
const KINDS: Record<Kind, string> = { promo: "直播预热", clip: "直播回放" };

function TaskTable({ tasks, error, loading }: { tasks: TaskSummary[]; error: string; loading: boolean }) {
  const formatter = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  if (error) return <p className="empty-table error" role="alert">{error}</p>;
  if (loading) return <p className="empty-table muted">正在读取任务…</p>;
  if (!tasks.length) return <div className="empty-table"><span className="empty-icon"><Clock3 size={22} /></span><strong>暂无任务</strong><p>新建预热或回放任务后，可在这里查看进度和成品。</p></div>;
  return <div className="table-scroll"><table>
    <thead><tr><th>任务名称</th><th>场景</th><th>状态</th><th>更新时间</th><th><span className="sr-only">打开</span></th></tr></thead>
    <tbody>{tasks.map(task => <tr key={task.id}>
      <td><a className="task-link" href={"#/task/" + task.id}>{task.title}<small>{audienceLabels[task.audience]} · {task.mode === "live" ? "实时" : "样例"}</small></a></td>
      <td>{KINDS[task.kind]}</td><td><StatusPill status={task.status} /></td><td>{formatter.format(new Date(task.updated_at))}</td>
      <td><a className="row-arrow" aria-label={"打开 " + task.title} href={"#/task/" + task.id}><ArrowUpRight size={19} /></a></td>
    </tr>)}</tbody>
  </table></div>;
}

function Workflows() {
  return <div className="workflow-grid">
    <a href="#/promo" className="workflow-card panel">
      <span className="workflow-icon preheat"><Sparkles size={23} /></span>
      <div className="workflow-body"><div className="eyebrow">直播前</div><h2>制作直播预热</h2><p>从活动简报生成海报、预热视频和群文案。</p></div>
      <span className="workflow-arrow"><ArrowUpRight size={22} /></span>
    </a>
    <a href="#/clip" className="workflow-card panel">
      <span className="workflow-icon replay"><Clapperboard size={23} /></span>
      <div className="workflow-body"><div className="eyebrow">直播后</div><h2>剪辑直播回放</h2><p>找出适合受众的片段，导出带字幕的竖屏成片。</p></div>
      <span className="workflow-arrow"><ArrowUpRight size={22} /></span>
    </a>
  </div>;
}

function Home({ tasks, error, loading }: { tasks: TaskSummary[]; error: string; loading: boolean }) {
  return <>
    <section className="hero">
      <div className="hero-text">
        <div className="hero-kicker"><span />保研直播运营</div>
        <h1>直播内容<br />从简报到成片</h1>
        <p>直播前做预热，直播后剪回放。<br />在一个工作台确认文案、画面和交付物。</p>
        <a className="button lime" href="#/promo"><Plus size={18} />制作预热</a>
      </div>
      <div className="hero-art" aria-hidden="true">
        <span className="orbit orbit-one" /><span className="orbit orbit-two" /><span className="orbit orbit-three" />
        <div className="art-slide"><img src="/assets/studio-slide.webp" alt="" /><span className="art-timeline"><i /><i /><i /><i /><i /></span></div>
        <div className="art-poster"><img src="/assets/studio-poster.webp" alt="" /></div>
        <span className="art-corner"><ArrowDownRight size={27} strokeWidth={1.5} /></span>
      </div>
    </section>
    <Workflows />
    <section className="panel tasks-panel">
      <div className="panel-heading"><div><h2>最近任务</h2><p>查看处理进度，继续审核和下载。</p></div><a className="button small" href="#/history">全部任务<ArrowRight size={16} /></a></div>
      <TaskTable tasks={tasks.slice(0, 5)} error={error} loading={loading} />
    </section>
  </>;
}

function HistoryPage({ tasks, error, loading }: { tasks: TaskSummary[]; error: string; loading: boolean }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Status | "all">("all");
  const filtered = tasks.filter(task => task.title.toLowerCase().includes(query.trim().toLowerCase()) && (status === "all" || task.status === status));
  return <>
    <div className="page-title"><h1>任务记录</h1><p>查找任务、恢复处理或下载已生成的成品。</p></div>
    <section className="panel tasks-panel">
      <div className="task-filters">
        <label className="search"><Search size={18} /><input type="search" placeholder="按任务名称搜索" aria-label="搜索任务" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <select value={status} onChange={event => setStatus(event.target.value as Status | "all")} aria-label="按状态筛选">
          <option value="all">所有状态</option>{Object.entries(statusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
        </select><span className="muted">{filtered.length} 个任务</span>
      </div>
      <TaskTable tasks={filtered} error={error} loading={loading} />
    </section>
  </>;
}

function App() {
  const [location, setLocation] = useState(route);
  const [config, setConfig] = useState<Config>();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [guide, setGuide] = useState(false);
  useEffect(() => {
    const navigate = () => { setLocation(route()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", navigate);
    request<Config>("/config").then(setConfig).catch(error => setError(apiError(error)));
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  useEffect(() => {
    if (location.page !== "home" && location.page !== "history") return;
    let active = true;
    async function load() {
      try {
        const result = await request<TaskSummary[]>("/tasks");
        if (active) { setTasks(result); setError(""); }
      } catch (error) { if (active) setError(apiError(error)); }
      finally { if (active) setLoading(false); }
    }
    void load();
    const timer = window.setInterval(() => { void load(); }, 3300);
    return () => { active = false; window.clearInterval(timer); };
  }, [location.page]);
  function open(task: Task) {
    window.location.hash = "/task/" + task.id;
  }
  const enabled = config?.live_promo || config?.live_clip;
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#/"><span><Film size={23} /></span><div><strong>保研内容</strong><small>直播运营工作台</small></div></a>
      <nav aria-label="工作台导航">
        {LINKS.map(([page, href, title, Icon], i) => <a key={page} href={href} className={(location.page === page || (location.page === "task" && page === "history") ? "active " : "") + (i === 2 ? "group-start" : "")}
          aria-current={location.page === page ? "page" : undefined}><Icon size={19} strokeWidth={1.8} /><span>{title}</span></a>)}
      </nav>
      <div className="sidebar-bottom"><span className={config ? "online" : ""} /><div><strong>{enabled ? "实时模型已配置" : config ? "样例模式可用" : "连接工作台…"}</strong><small>{config?.team_access ? "团队专用" : "本地工作区"}</small></div></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span>{PAGE_NAMES[location.page]}</span><button className="button small quiet" onClick={() => setGuide(true)}><CircleHelp size={17} />使用指南</button></header>
      <main className="main">
        {location.page === "home" && <Home tasks={tasks} error={error} loading={loading} />}
        {location.page === "history" && <HistoryPage tasks={tasks} error={error} loading={loading} />}
        {location.page === "promo" && <PromoCreate config={config} onCreate={open} />}
        {location.page === "clip" && <ClipCreate config={config} onCreate={open} />}
        {location.page === "task" && location.id && <TaskScreen key={location.id} id={location.id} />}
      </main>
    </div>
    {guide && <div className="dialog-backdrop" onClick={() => setGuide(false)}>
      <section className="panel dialog" role="dialog" aria-modal="true" aria-labelledby="guide-title" onClick={event => event.stopPropagation()}>
        <div className="panel-heading"><h2 id="guide-title">使用指南</h2><button className="button square" autoFocus aria-label="关闭" onClick={() => setGuide(false)}><X size={18} /></button></div>
        <p><strong>做直播预热</strong>时，填写活动信息和议题。确认分镜后，工作台会导出海报、预热视频和群文案。</p>
        <p><strong>剪直播回放</strong>时，上传录屏与字幕，选择推荐片段并确认切点。成片页面提供单项下载和整包下载。</p>
        <p>样例模式使用本地素材，并实际执行渲染和剪辑。实时模式可调用后台配置的模型服务。</p>
      </section>
    </div>}
  </div>;
}

createRoot(document.getElementById("root")!).render(<App />);
