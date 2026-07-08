// TexTrans 后端 REST 客户端封装。经 next.config rewrites 代理到 FastAPI。

export interface TaskArtifacts {
  translated_pdf: string | null
  bilingual_pdf: string | null
  original_pdf: string | null
}

export interface TaskStatus {
  task_id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  stage: string
  message: string
  progress_current: number
  progress_total: number
  artifacts: TaskArtifacts
  error: string | null
  title?: string | null
  source?: string | null
  created_at?: number | null
}

export interface CreateTaskResponse {
  task_id: string
  status: string
}

export interface CreateTaskParams {
  arxiv_url: string
  provider?: string
  make_bilingual?: boolean
  workers?: number
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

// 通过 arXiv 链接/ID 创建任务
export async function createTask(params: CreateTaskParams): Promise<CreateTaskResponse> {
  const res = await fetch('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'arxiv', ...params }),
  })
  return jsonOrThrow<CreateTaskResponse>(res)
}

// 上传源码压缩包创建任务
export async function uploadTask(
  file: File,
  opts: { provider?: string; make_bilingual?: boolean; workers?: number } = {},
): Promise<CreateTaskResponse> {
  const form = new FormData()
  form.append('file', file)
  if (opts.provider) form.append('provider', opts.provider)
  form.append('make_bilingual', String(opts.make_bilingual ?? true))
  form.append('workers', String(opts.workers ?? 8))
  const res = await fetch('/api/tasks/upload', { method: 'POST', body: form })
  return jsonOrThrow<CreateTaskResponse>(res)
}

export async function getTask(taskId: string): Promise<TaskStatus> {
  const res = await fetch(`/api/tasks/${taskId}`)
  return jsonOrThrow<TaskStatus>(res)
}

export async function listTasks(): Promise<TaskStatus[]> {
  const res = await fetch('/api/tasks')
  return jsonOrThrow<TaskStatus[]>(res)
}

export type ArtifactKind = 'translated' | 'bilingual' | 'original'

// 下载链接(带论文标题文件名,浏览器另存为)
export function downloadUrl(taskId: string, kind: ArtifactKind): string {
  return `/api/tasks/${taskId}/download/${kind}`
}

// 预览链接(inline,供 iframe 在页面内渲染而非触发下载)
export function previewUrl(taskId: string, kind: ArtifactKind): string {
  return `/api/tasks/${taskId}/download/${kind}?inline=true`
}
