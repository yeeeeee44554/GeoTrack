const fallbackBase = '/demo_seed.json'

async function getJson(url) {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json()
}

function withQuery(path, params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '' && value !== 'all') {
      search.set(key, String(value))
    }
  })
  const query = search.toString()
  return query ? `${path}?${query}` : path
}

export function queryTrajectories(params = {}) {
  return getJson(withQuery('/api/query/trajectories', params))
}

export function queryFullTrajectories(params = {}) {
  return getJson(withQuery('/api/full/trajectories', params))
}

export function queryHotspots(params = {}) {
  return getJson(withQuery('/api/query/hotspots', params))
}

export function queryFullHotspots(params = {}) {
  return getJson(withQuery('/api/full/hotspots', params))
}

export function getTrajectory(trajectoryId) {
  return getJson(`/api/trajectories/${encodeURIComponent(trajectoryId)}`)
}

export function getFullTrajectory(trajectoryId) {
  return getJson(`/api/full/trajectories/${encodeURIComponent(trajectoryId)}`)
}

export function getSpatiotemporalAt(trajectoryId, ts) {
  return getJson(withQuery('/api/full/spatiotemporal/at', { trajectory_id: trajectoryId, ts }))
}

export function getJob(jobId) {
  return getJson(`/api/jobs/${encodeURIComponent(jobId)}`)
}
export async function loadDashboardData() {
  try {
    // Probe the cheap health endpoint first.  An optional full index should
    // not create a noisy 404 in the browser console on every normal demo load.
    const health = await getJson('/api/health')
    const full = health.full_index_available ? await getJson('/api/full/summary') : null
    const prefix = full?.available ? '/api/full' : '/api'
    const [summary, users, trajectories, hotspots, patterns, quality] = await Promise.all([
      full?.available ? Promise.resolve(full.summary) : getJson('/api/summary'),
      getJson(`${prefix}/users?limit=100`),
      getJson(`${prefix}/trajectories?limit=100`),
      getJson(`${prefix}/hotspots?limit=30`),
      full?.available ? getJson(`${prefix}/patterns`) : getJson('/api/patterns/clusters'),
      full?.available ? Promise.resolve(full.quality) : getJson('/api/data-quality'),
    ])
    return { summary, users, trajectories, hotspots, patterns, quality, mode: full?.available ? 'full' : 'api', fullSummary: full }
  } catch (error) {
    const seed = await getJson(fallbackBase)
    return { ...seed, mode: 'demo', error: error.message }
  }
}

export async function runJob(job_type = 'mine') {
  const response = await fetch('/api/jobs/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_type }),
  })
  if (!response.ok) throw new Error('任务提交失败')
  return response.json()
}
