export type Repository = {
  full_name: string
  imported_at: string
  document_count: number
  metadata: { description?: string; stargazers_count?: number; language?: string }
}

export type Evidence = {
  id: string
  kind: 'issue' | 'pull_request' | 'commit' | 'doc'
  title: string
  url: string
  number?: number
  score: number
  reasons: string[]
  excerpt: string
}

export type Investigation = {
  id: string
  repository: string
  question: string
  answer: string
  confidence: 'low' | 'medium' | 'high'
  evidence: Evidence[]
  trace: Array<{ name: string; status: string; duration_ms: number; output?: Record<string, unknown> }>
  used_llm: boolean
}

export type Evaluation = {
  dataset: string
  cases: number
  metrics: Record<string, number>
  variants: Array<{ id: string; label: string; 'hit_rate@5': number; mrr: number }>
  note: string
}
