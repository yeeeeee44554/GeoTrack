import { useCallback, useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import {
  Activity,
  BarChart3,
  Database,
  Gauge,
  Layers3,
  ListFilter,
  Map,
  Menu,
  Play,
  Radar,
  RefreshCw,
  Route,
  Server,
  Sparkles,
  Target,
  X,
} from 'lucide-react'
import { getFullTrajectory, getJob, getSpatiotemporalAt, getTrajectory, loadDashboardData, queryFullHotspots, queryFullTrajectories, queryHotspots, queryTrajectories, runJob } from './lib/api.js'
import MapPanel from './components/MapPanel.jsx'
import SectionHeading from './components/SectionHeading.jsx'
import StatCard from './components/StatCard.jsx'

const navItems = [
  { id: 'overview', label: '数据总览', icon: Gauge },
  { id: 'trajectories', label: '轨迹探索', icon: Route },
  { id: 'hotspots', label: '热点分析', icon: Target },
  { id: 'patterns', label: '出行模式', icon: Radar },
]

const fmt = (value) => new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value ?? 0)
const km = (value) => `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format((value ?? 0) / 1000)} km`

const PATTERN_DESCRIPTIONS = {
  早晚通勤型: '早晚高峰明显，作息规律的通勤人群',
  高频全天型: '出行频繁，全天各时段均有活动',
  午后夜间活动型: '活动集中在午后至深夜，出行量较少',
}
const patternDescription = (label) => PATTERN_DESCRIPTIONS[label] ?? '按出行时段聚类的用户群体'

function useDashboardData() {
  const [state, setState] = useState({ loading: true, data: null, error: null })
  const refresh = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: null }))
    loadDashboardData()
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((error) => setState({ loading: false, data: null, error: error.message }))
  }, [])
  useEffect(refresh, [refresh])
  return { ...state, refresh }
}
function AppShell({ activeView, setActiveView, children, dataMode, onRefresh, mobileNav, setMobileNav }) {
  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <button className="sidebar-close" onClick={() => setMobileNav(false)} aria-label="关闭侧边导航"><X size={18} /></button>
        <div className="brand-lockup">
          <div className="brand-mark"><span /><span /><span /></div>
          <div><strong>GeoTrack</strong></div>
        </div>
        <div className="sidebar-caption">工作台</div>
        <nav>
          {navItems.map(({ id, label, icon: Icon }) => (
            <button key={id} className={activeView === id ? 'nav-item active' : 'nav-item'} onClick={() => { setActiveView(id); setMobileNav(false) }}>
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>{activeView === id && <i />}
            </button>
          ))}
        </nav>
      </aside>
      {mobileNav && <button aria-label="关闭导航" className="mobile-backdrop" onClick={() => setMobileNav(false)} />}
      <main className="main-shell">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setMobileNav(true)} aria-label="打开导航"><Menu size={20} /></button>
          <div className="breadcrumb"><span>GeoTrack</span><b>/</b><strong>{navItems.find((item) => item.id === activeView)?.label}</strong></div>
          <div className="topbar-actions">
            <button className="icon-button" onClick={onRefresh} title="刷新数据"><RefreshCw size={16} /></button>
          </div>
        </header>
        {children}
      </main>
    </div>
  )
}

function PageHeader({ kicker, title, description, action }) {
  return <div className="page-header"><div><div className="page-kicker">{kicker}</div>{description ? <p>{description}</p> : null}</div>{action}</div>
}

function TrendChart({ patterns }) {
  const series = useMemo(() => {
    const values = patterns?.[0]?.hourly_profile ?? [0.01,0.01,0.01,0.01,0.02,0.04,0.09,0.13,0.12,0.08,0.05,0.04,0.04,0.04,0.05,0.06,0.07,0.08,0.07,0.05,0.04,0.03,0.02,0.01]
    return values.map((value) => Math.round(value * 1000) / 10)
  }, [patterns])
  const option = { animationDuration: 700, grid: { left: 2, right: 8, top: 10, bottom: 22, containLabel: true }, tooltip: { trigger: 'axis', backgroundColor: '#13283a', borderColor: '#29445b', textStyle: { color: '#eaf4f0' } }, xAxis: { type: 'category', boundaryGap: false, data: Array.from({ length: 24 }, (_, index) => `${String(index).padStart(2, '0')}:00`), axisLabel: { color: '#7e97a9', interval: 3 }, axisLine: { lineStyle: { color: '#274052' } } }, yAxis: { type: 'value', axisLabel: { color: '#7e97a9', formatter: '{value}%' }, splitLine: { lineStyle: { color: '#1d3344' } } }, series: [{ data: series, type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 3, color: '#44ddbb' }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(68,221,187,.28)' }, { offset: 1, color: 'rgba(68,221,187,0)' }] } } }] }
  return <ReactECharts option={option} style={{ height: 236, width: '100%' }} opts={{ renderer: 'svg' }} />
}

function HotspotList({ hotspots, selected, onSelect }) {
  return <div className="hotspot-list">{hotspots.slice(0, 4).map((hotspot, index) => <button key={hotspot.hotspot_id} className={`hotspot-row ${selected?.hotspot_id === hotspot.hotspot_id ? 'selected' : ''}`} onClick={() => onSelect?.(hotspot)}><span className="rank">0{index + 1}</span><span className="hotspot-name"><strong>{hotspot.hotspot_id}</strong><small>{hotspot.center.latitude.toFixed(3)}°N · {hotspot.center.longitude.toFixed(3)}°E</small></span><span className="hotspot-value"><strong>{fmt(hotspot.visit_count)}</strong><small>访问次数</small></span><span className="hotspot-arrow">↗</span></button>)}</div>
}

function Overview({ data, setActiveView }) {
  const [selectedHotspot, setSelectedHotspot] = useState(data.hotspots?.[0])
  const summary = data.summary ?? {}
  const fullCounts = data.fullSummary?.summary ?? null
  return <div className="page-content">
    <PageHeader title="看见城市如何移动" action={<button className="primary-button" onClick={() => setActiveView('hotspots')}><Sparkles size={16} />探索热点</button>} />
    <div className="stat-grid">
      <StatCard label="轨迹点" value={fmt(summary.point_count)} hint={data.mode === 'full' ? '全量索引有效点' : '当前演示子集'} icon={<Activity size={15} />} />
      <StatCard label="轨迹数量" value={fmt(summary.trajectory_count)} hint={data.mode === 'full' ? '全量分页查询' : '演示轨迹记录'} tone="orange" icon={<Route size={15} />} />
      <StatCard label="覆盖用户" value={fmt(summary.user_count)} hint={data.mode === 'full' ? '全量匿名用户' : '演示子集用户'} tone="blue" icon={<Layers3 size={15} />} />
    </div>
    <div className="dashboard-grid top-grid">
      <section className="panel map-panel"><SectionHeading eyebrow="SPATIAL VIEW" title="北京 · 轨迹密度" meta={data.mode === 'full' ? '全量索引 · 采样显示' : '演示子集 / 500m DBSCAN'} /><MapPanel trajectories={data.trajectories} hotspots={data.hotspots} selectedHotspot={selectedHotspot} onHotspotSelect={setSelectedHotspot} /><div className="map-footer"><span><i className="pulse-dot" />数据链路正常</span><button onClick={() => setActiveView('trajectories')}>查看轨迹明细 <span>→</span></button></div></section>
      <section className="panel hotspot-panel"><SectionHeading eyebrow="TOP AREAS" title="热点区域" meta="按访问次数排序" /><HotspotList hotspots={data.hotspots} selected={selectedHotspot} onSelect={setSelectedHotspot} /><div className="panel-link"><button onClick={() => setActiveView('hotspots')}>进入热点分析 <span>→</span></button></div></section>
    </div>
    <div className="dashboard-grid bottom-grid">
      <section className="panel trend-panel"><SectionHeading eyebrow="TEMPORAL SIGNAL" title="一天中的出行节奏" meta="24h profile" /><TrendChart patterns={data.patterns} /></section>
    </div>
  </div>
}

function TrajectoryView({ data }) {
  const pageSize = 12
  const [user, setUser] = useState('all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [page, setPage] = useState(0)
  const [rows, setRows] = useState(data.trajectories ?? [])
  const [selected, setSelected] = useState(data.trajectories?.[0])
  const [detail, setDetail] = useState(null)
  const [detailState, setDetailState] = useState({ loading: false, error: '' })
  const [queryState, setQueryState] = useState({ loading: false, error: '' })
  const [timePct, setTimePct] = useState(0)
  const [timePoint, setTimePoint] = useState(null)
  const [timeState, setTimeState] = useState({ loading: false, error: '' })

  useEffect(() => {
    let cancelled = false
    const start = startDate ? `${startDate}T00:00:00Z` : undefined
    const end = endDate ? `${endDate}T23:59:59Z` : undefined
    setQueryState({ loading: true, error: '' })

    if (data.mode === 'demo') {
      const filtered = (data.trajectories ?? []).filter((row) => (
        (user === 'all' || row.user_id === user)
        && (!start || row.end_ts >= start)
        && (!end || row.start_ts <= end)
      ))
      setRows(filtered.slice(page * pageSize, (page + 1) * pageSize))
      setQueryState({ loading: false, error: '' })
      return () => { cancelled = true }
    }

    const query = data.mode === 'full' ? queryFullTrajectories : queryTrajectories
    query({
      user_id: user,
      start,
      end,
      limit: pageSize,
      offset: page * pageSize,
    }).then((result) => {
      if (!cancelled) {
        setRows(result)
        setQueryState({ loading: false, error: '' })
      }
    }).catch((error) => {
      if (!cancelled) {
        setRows([])
        setQueryState({ loading: false, error: `轨迹查询失败：${error.message}` })
      }
    })
    return () => { cancelled = true }
  }, [data.mode, data.trajectories, user, startDate, endDate, page])

  useEffect(() => {
    setSelected((current) => rows.find((row) => row.trajectory_id === current?.trajectory_id) ?? rows[0])
  }, [rows])

  useEffect(() => {
    if (!selected?.trajectory_id) {
      setDetail(null)
      return undefined
    }
    if (data.mode === 'demo') {
      setDetail(selected)
      setDetailState({ loading: false, error: '' })
      return undefined
    }
    let cancelled = false
    setDetailState({ loading: true, error: '' })
    const getDetail = data.mode === 'full' ? getFullTrajectory : getTrajectory
    getDetail(selected.trajectory_id).then((result) => {
      if (!cancelled) {
        setDetail(result)
        setDetailState({ loading: false, error: '' })
      }
    }).catch((error) => {
      if (!cancelled) {
        setDetail(selected)
        setDetailState({ loading: false, error: `详情加载失败：${error.message}` })
      }
    })
    return () => { cancelled = true }
  }, [data.mode, selected])

  const resetPage = (setter) => (event) => {
    setter(event.target.value)
    setPage(0)
  }

  useEffect(() => { setTimePoint(null); setTimePct(0); setTimeState({ loading: false, error: '' }) }, [selected?.trajectory_id])

  const tsAtPct = (pct) => {
    if (!detail?.start_ts || !detail?.end_ts) return ''
    const s = new Date(detail.start_ts).getTime()
    const e = new Date(detail.end_ts).getTime()
    if (!Number.isFinite(s) || !Number.isFinite(e)) return ''
    const ratio = Math.max(0, Math.min(1, pct / 100))
    return new Date(s + ratio * (e - s)).toISOString().slice(0, 19)
  }

  const queryTimePoint = (pct) => {
    const ts = tsAtPct(pct)
    if (data.mode !== 'full' || !selected?.trajectory_id || !ts) return
    setTimeState({ loading: true, error: '' })
    getSpatiotemporalAt(selected.trajectory_id, ts).then((result) => {
      if (result?.position?.coordinates?.length === 2) {
        setTimePoint({ latitude: result.position.coordinates[1], longitude: result.position.coordinates[0] })
        setTimeState({ loading: false, error: '' })
      } else {
        setTimePoint(null)
        setTimeState({ loading: false, error: '未取到该时刻位置' })
      }
    }).catch((error) => {
      setTimePoint(null)
      setTimeState({ loading: false, error: `时刻查询失败：${error.message}` })
    })
  }

  useEffect(() => {
    if (data.mode !== 'full' || !selected?.trajectory_id || !detail?.start_ts) return undefined
    const timer = window.setTimeout(() => queryTimePoint(timePct), 200)
    return () => window.clearTimeout(timer)
  }, [timePct, selected?.trajectory_id, detail?.start_ts, detail?.end_ts, data.mode])

  return <div className="page-content">
    <PageHeader kicker="TRAJECTORY EXPLORER / 02" title="沿着用户轨迹走一遍" action={<div className="filter-stack"><div className="select-wrap"><ListFilter size={15} /><select value={user} onChange={resetPage(setUser)}><option value="all">全部用户</option>{data.users?.map((item) => <option key={item.user_id} value={item.user_id}>{item.user_id} · {item.trajectory_count} 条</option>)}</select></div></div>} />
    <div className="dashboard-grid explorer-grid">
      <section className="panel map-panel"><SectionHeading eyebrow="TRACE PREVIEW" title={selected?.trajectory_id ?? '选择一条轨迹'} meta={detailState.loading ? '详情查询中…' : detail ? `${detail.point_count} points` : '等待选择'} />{detailState.error ? <div className="inline-state error detail-error">{detailState.error}</div> : null}<MapPanel trajectories={detail ? [detail] : selected ? [selected] : []} hotspots={data.hotspots} focusPoint={timePoint} /><div className="trajectory-summary"><div><span>开始时间</span><strong>{detail?.start_ts?.slice(0, 16).replace('T', ' ') ?? '—'}</strong></div><div><span>距离</span><strong>{detail ? km(detail.distance_m) : '—'}</strong></div><div><span>持续时间</span><strong>{detail ? `${Math.round((detail.duration_s ?? 0) / 60)} min` : '—'}</strong></div></div><div className="time-query"><span className="time-query-label"><Target size={14} />时刻定位</span><input type="range" min="0" max="100" step="1" value={timePct} onChange={(event) => setTimePct(Number(event.target.value))} disabled={data.mode !== 'full'} /><span className="time-query-ts">{tsAtPct(timePct).replace('T', ' ') || '—'}</span>{timeState.error ? <span className="time-query-error">{timeState.error}</span> : timePoint ? <span className="time-query-result">{timePoint.latitude.toFixed(5)}, {timePoint.longitude.toFixed(5)}</span> : null}</div></section>
      <section className="panel table-panel"><SectionHeading eyebrow="TRAJECTORIES" title="轨迹记录" meta={queryState.loading ? '查询中…' : `${rows.length} records`} />{queryState.error ? <div className="inline-state error">{queryState.error}</div> : queryState.loading ? <div className="inline-state">正在按筛选条件查询轨迹…</div> : rows.length === 0 ? <div className="inline-state">当前筛选条件下没有轨迹</div> : <div className="data-table"><div className="table-head"><span>ID</span><span>用户</span><span>距离</span><span>时间</span></div>{rows.map((row) => <button key={row.trajectory_id} className={`table-row ${selected?.trajectory_id === row.trajectory_id ? 'selected' : ''}`} onClick={() => setSelected(row)}><span>{row.trajectory_id.split('_')[1] ?? row.trajectory_id}</span><span className="user-chip">{row.user_id}</span><span>{km(row.distance_m)}</span><span>{row.start_ts.slice(0, 10)}</span></button>)}</div>}<div className="pagination"><button disabled={page === 0 || queryState.loading} onClick={() => setPage((current) => Math.max(0, current - 1))}>上一页</button><span>第 {page + 1} 页</span><button disabled={rows.length < pageSize || queryState.loading} onClick={() => setPage((current) => current + 1)}>下一页</button></div></section>
    </div>
  </div>
}
function HotspotView({ data }) {
  const [minUsers, setMinUsers] = useState(0)
  const [eps, setEps] = useState(500)
  const [minPts, setMinPts] = useState(3)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [rows, setRows] = useState(data.hotspots ?? [])
  const [selected, setSelected] = useState(data.hotspots?.[0])
  const [queryState, setQueryState] = useState({ loading: false, error: '' })

  useEffect(() => {
    let cancelled = false
    setQueryState({ loading: true, error: '' })
    const timer = window.setTimeout(() => {
      if (data.mode === 'demo') {
        setRows((data.hotspots ?? []).filter((item) => item.unique_users >= minUsers))
        setQueryState({ loading: false, error: '' })
        return
      }
      const query = data.mode === 'full' ? queryFullHotspots : queryHotspots
      const params = data.mode === 'full'
        ? { min_users: minUsers, limit: 30 }
        : {
            min_users: minUsers,
            eps,
            minPts,
            start: startDate ? `${startDate}T00:00:00Z` : undefined,
            end: endDate ? `${endDate}T23:59:59Z` : undefined,
            limit: 30,
          }
      query(params).then((result) => {
        if (!cancelled) {
          setRows(result)
          setQueryState({ loading: false, error: '' })
        }
      }).catch((error) => {
        if (!cancelled) {
          setRows([])
          setQueryState({ loading: false, error: `热点查询失败：${error.message}` })
        }
      })
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [data.mode, data.hotspots, minUsers, eps, minPts, startDate, endDate])

  useEffect(() => {
    setSelected((current) => rows.find((row) => row.hotspot_id === current?.hotspot_id) ?? rows[0])
  }, [rows])

  return <div className="page-content">
    <PageHeader kicker="HOTSPOT MINING / 03" title="城市的高密度脉搏" action={<div className="filter-stack hotspot-filters"><div className="control-row"><span className="control-label">最少用户</span><input type="range" min="0" max="100" step="10" value={minUsers} onChange={(event) => setMinUsers(Number(event.target.value))} /><strong>{minUsers}</strong></div></div>} />
    <div className="dashboard-grid hotspot-view-grid">
      <section className="panel map-panel"><SectionHeading eyebrow="DBSCAN RESULT" title="空间聚类结果" meta={`eps ${eps}m · minPts ${minPts}`} />{queryState.error ? <div className="inline-state error">{queryState.error}</div> : queryState.loading ? <div className="inline-state map-state">正在查询热点结果…</div> : rows.length === 0 ? <div className="inline-state map-state">当前参数下没有识别到热点</div> : <MapPanel trajectories={data.trajectories} hotspots={rows} selectedHotspot={selected} onHotspotSelect={setSelected} />}<div className="selected-detail">{selected ? <><div><span>选中热点</span><strong>{selected.hotspot_id}</strong></div><div><span>访问次数</span><strong>{fmt(selected.visit_count)}</strong></div><div><span>峰值时段</span><strong>{String(selected.peak_hour).padStart(2, '0')}:00</strong></div><div><span>平均停留</span><strong>{Math.round(selected.avg_dwell_s / 60)} min</strong></div></> : <span>调整参数或日期范围后查看热点详情</span>}</div></section>
      <section className="panel hotspot-panel"><SectionHeading eyebrow="RANKING" title="热点排名" meta={queryState.loading ? '查询中…' : `${rows.length} clusters`} />{!queryState.loading && !queryState.error && rows.length > 0 ? <HotspotList hotspots={rows} selected={selected} onSelect={setSelected} /> : <div className="inline-state">{queryState.error || (queryState.loading ? '等待后端返回结果…' : '暂无热点排名')}</div>}</section>
    </div>
  </div>
}
function PatternView({ data }) {
  const [activePattern, setActivePattern] = useState(data.patterns?.[0])
  const option = { animationDuration: 650, grid: { left: 10, right: 24, top: 20, bottom: 22, containLabel: true }, tooltip: { trigger: 'axis', backgroundColor: '#13283a', borderColor: '#29445b', textStyle: { color: '#eaf4f0' } }, legend: { top: 0, right: 0, textStyle: { color: '#8aa2b2' }, data: data.patterns?.map((item) => item.label) }, xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, index) => String(index).padStart(2, '0')), axisLabel: { color: '#7e97a9', interval: 0 }, axisLine: { lineStyle: { color: '#274052' } } }, yAxis: { type: 'value', axisLabel: { color: '#7e97a9', formatter: '{value}%' }, splitLine: { lineStyle: { color: '#1d3344' } } }, series: data.patterns?.map((item, index) => { const active = activePattern?.pattern_id === item.pattern_id; const color = ['#45e0c2', '#ffb36a', '#a78bfa'][index % 3]; return { name: item.label, type: 'line', smooth: true, symbol: 'none', data: item.hourly_profile.map((value) => Math.round(value * 1000) / 10), lineStyle: { width: active ? 4 : 2, opacity: active ? 1 : 0.25, color }, itemStyle: { color }, z: active ? 10 : 1 } }) }
  return <div className="page-content"><PageHeader kicker="TRAVEL PATTERNS / 04" title="用户如何分成不同节奏" /><section className="panel pattern-chart-panel"><SectionHeading eyebrow="HOURLY PROFILES" title="三类时段模式" meta="归一化频率" /><ReactECharts option={option} notMerge style={{ height: 330 }} opts={{ renderer: 'svg' }} /></section><div className="pattern-cards">{data.patterns?.map((pattern, index) => <button key={pattern.pattern_id} className={`pattern-card ${activePattern?.pattern_id === pattern.pattern_id ? 'active' : ''}`} onClick={() => setActivePattern(pattern)}><div className={`pattern-index index-${index}`}>0{index + 1}</div><div><span>CLUSTER {pattern.cluster_id + 1}</span><h3>{pattern.label}</h3><p>{patternDescription(pattern.label)}</p></div><div className="pattern-stat"><strong>{pattern.user_count}</strong><small>用户</small></div><div className="pattern-stat"><strong>{(pattern.avg_distance_m / 1000).toFixed(0)} km</strong><small>人均里程</small></div></button>)}</div></div>
}

function QualityView({ data, onRefresh }) {
  const [running, setRunning] = useState(false)
  const [job, setJob] = useState(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!job?.job_id || ['completed', 'failed'].includes(job.status)) return undefined
    let cancelled = false
    const poll = window.setInterval(() => {
      getJob(job.job_id).then((next) => {
        if (!cancelled) setJob(next)
      }).catch((error) => {
        if (!cancelled) setMessage(`任务状态查询失败：${error.message}`)
      })
    }, 1200)
    return () => {
      cancelled = true
      window.clearInterval(poll)
    }
  }, [job])

  useEffect(() => {
    if (!job) return
    if (job.status === 'completed') {
      setMessage(`任务 ${job.job_id} 已完成，服务数据已刷新。`)
      onRefresh()
    } else if (job.status === 'failed') {
      setMessage(`任务 ${job.job_id} 失败：${job.error || job.message || '未知错误'}`)
    } else {
      setMessage(`任务 ${job.job_id}：${job.message || job.status}`)
    }
  }, [job, onRefresh])

  async function handleRun() {
    setRunning(true)
    setMessage('正在提交 Spark 任务…')
    try {
      const next = await runJob('mine')
      setJob(next)
      setMessage(`任务 ${next.job_id} 已进入队列`)
    } catch (error) {
      setMessage('API 未连接：当前处于本地演示模式')
    } finally {
      setRunning(false)
    }
  }
  const quality = data.quality ?? {}
  const statusLabel = { queued: '排队中', running: '运行中', completed: '已完成', failed: '失败' }
  return <div className="page-content"><PageHeader kicker="PIPELINE OPS / 05" title="让每一批数据都有迹可循" description="查看数据质量、处理批次与 Spark 任务入口，保证结果可复现、可答辩。" action={<button className="primary-button" onClick={handleRun} disabled={running || ['queued', 'running'].includes(job?.status)}>{running ? <RefreshCw className="spin" size={16} /> : <Play size={16} />}{running ? '提交中' : job?.status === 'running' ? '运行中' : '运行挖掘任务'}</button>} /><div className="dashboard-grid quality-grid"><section className="panel"><SectionHeading eyebrow="QUALITY REPORT" title="清洗摘要" meta="当前数据集" /><div className="quality-metrics"><div><span>有效点</span><strong>{fmt(quality.valid_points)}</strong><small>保留进入特征工程</small></div><div><span>重复点</span><strong>{fmt(quality.duplicate_points)}</strong><small>连续重复坐标时间点</small></div><div><span>时间断点</span><strong>{fmt(quality.time_gap_segments)}</strong><small>超过 30 分钟</small></div><div><span>停留点</span><strong>{fmt(quality.stay_point_count)}</strong><small>200m / 20min 规则</small></div></div><div className="quality-progress"><div><span>点级有效率</span><strong>99.3%</strong></div><div className="progress-track"><i style={{ width: '99.3%' }} /></div></div></section><section className="panel"><SectionHeading eyebrow="RUNBOOK" title="处理链路" meta="四层架构" /><div className="pipeline-list"><div className="pipeline-item done"><span>01</span><div><strong>PLT / HDFS raw</strong><small>原始轨迹文件落盘</small></div><i>✓</i></div><div className="pipeline-item done"><span>02</span><div><strong>Spark clean</strong><small>清洗、距离、质量报告</small></div><i>✓</i></div><div className="pipeline-item active"><span>03</span><div><strong>MobilityDB serving</strong><small>空间索引与时态轨迹</small></div><i>●</i></div><div className="pipeline-item"><span>04</span><div><strong>REST / React</strong><small>查询、地图和图表展示</small></div><i>○</i></div></div><div className={`job-message ${job?.status === 'failed' ? 'job-failed' : ''}`}>{job ? <><strong>{statusLabel[job.status] || job.status}</strong> · {message}{job.started_at ? <small>开始 {job.started_at.slice(11, 19)} UTC</small> : null}</> : message || '批处理任务可以在 Docker/Spark 环境中替换为真实 spark-submit。'}</div></section></div><section className="panel implementation-note"><Server size={20} /><div><strong>课程答辩提示</strong><p>演示时说明：HDFS 保存 raw/curated Parquet，Spark 生成停留点和聚类结果，MobilityDB 负责空间检索，FastAPI 只查询预计算服务表，避免网页请求阻塞批处理。</p></div><button className="ghost-button" onClick={onRefresh}>刷新数据</button></section></div>
}
export default function App() {
  const { loading, data, error, refresh } = useDashboardData()
  const [activeView, setActiveView] = useState('overview')
  const [mobileNav, setMobileNav] = useState(false)
  useEffect(() => {
    if (!mobileNav) return undefined
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setMobileNav(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [mobileNav])
  if (loading && !data) return <div className="loading-screen"><div className="loading-mark"><span /><span /><span /></div><strong>正在加载轨迹工作台</strong><small>连接 API / 读取演示数据</small></div>
  if (error && !data) return <div className="error-screen"><Database size={28} /><h1>数据服务暂时不可用</h1><p>{error}</p><button className="primary-button" onClick={refresh}>重试</button></div>
  const view = activeView === 'overview' ? <Overview data={data} setActiveView={setActiveView} /> : activeView === 'trajectories' ? <TrajectoryView data={data} /> : activeView === 'hotspots' ? <HotspotView data={data} /> : <PatternView data={data} />
  return <AppShell activeView={activeView} setActiveView={setActiveView} dataMode={data.mode} onRefresh={refresh} mobileNav={mobileNav} setMobileNav={setMobileNav}>{view}</AppShell>
}
