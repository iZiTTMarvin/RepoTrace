import type { Evaluation, Investigation, Repository } from './types'

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(body.detail ?? '请求失败')
  }
  return response.json() as Promise<T>
}

export const api = {
  repositories: () => fetch('/api/repositories').then(json<Repository[]>),
  evaluation: () => fetch('/api/evaluation/demo').then(json<Evaluation>),
  importRepository: (repository: string) =>
    fetch('/api/repositories/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repository }),
    }).then(json<{ repository: string; document_count: number; counts: Record<string, number> }>),
  investigate: (repository: string, question: string) =>
    fetch('/api/investigations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repository, question }),
    }).then(json<Investigation>),
}
