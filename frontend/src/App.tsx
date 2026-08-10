import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  ArrowUpRight,
  BookOpenText,
  CheckCircle2,
  CircleDot,
  GitCommitHorizontal,
  GitMerge,
  Github,
  LoaderCircle,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { api } from './api'
import type { Evaluation, Evidence, Investigation, Repository } from './types'

const kindLabel: Record<Evidence['kind'], string> = {
  issue: 'Issue',
  pull_request: 'Pull Request',
  commit: 'Commit',
  doc: '文档',
}

const kindIcon = {
  issue: CircleDot,
  pull_request: GitMerge,
  commit: GitCommitHorizontal,
  doc: BookOpenText,
}

export default function App() {
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null)
  const [selected, setSelected] = useState('')
  const [repoInput, setRepoInput] = useState('')
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<Investigation | null>(null)
  const [busy, setBusy] = useState<'import' | 'investigate' | null>(null)
  const [error, setError] = useState('')

  const refresh = async () => {
    const repos = await api.repositories()
    setRepositories(repos)
    if (!selected && repos[0]) setSelected(repos[0].full_name)
  }

  useEffect(() => {
    void refresh().catch(() => undefined)
    void api.evaluation().then(setEvaluation).catch(() => undefined)
  }, [])

  const selectedRepo = useMemo(
    () => repositories.find((repo) => repo.full_name === selected),
    [repositories, selected],
  )

  const importRepo = async () => {
    if (!repoInput.trim()) return
    setBusy('import')
    setError('')
    try {
      const imported = await api.importRepository(repoInput.trim())
      setRepoInput('')
      await refresh()
      setSelected(imported.repository)
    } catch (err) {
      setError(err instanceof Error ? err.message : '导入失败')
    } finally {
      setBusy(null)
    }
  }

  const investigate = async () => {
    if (!selected || !question.trim()) return
    setBusy('investigate')
    setError('')
    try {
      setResult(await api.investigate(selected, question.trim()))
    } catch (err) {
      setError(err instanceof Error ? err.message : '调查失败')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Search size={18} /></div>
          <div><strong>RepoTrace</strong><span>历史故障调查</span></div>
        </div>
        <div className="topbar-meta"><span className="status-dot" /> 本地服务</div>
      </header>

      <main>
        <section className="hero-grid">
          <div className="hero-copy">
            <div className="eyebrow"><Sparkles size={15} /> Evidence-first debugging</div>
            <h1>先查清项目过去发生过什么，<br />再决定现在怎么修。</h1>
            <p>RepoTrace 把散落在 Issue、PR、Commit 和项目文档里的历史信息串起来，帮助开发者快速定位相似故障、历史根因和对应修复。</p>
          </div>
          <div className="metric-card">
            <div className="metric-head"><Activity size={17} /> 内置检索回归</div>
            <div className="metric-big">{evaluation ? `${Math.round(evaluation.metrics['hit_rate@5'] * 100)}%` : '—'}</div>
            <div className="metric-label">Hit Rate @ 5</div>
            <div className="metric-foot">{evaluation?.cases ?? '—'} 个可重复故障样例 · MRR {evaluation?.metrics.mrr ?? '—'}</div>
          </div>
        </section>

        <section className="workspace-grid">
          <aside className="side-panel panel">
            <div className="panel-title"><Github size={17} /> 仓库</div>
            <div className="import-row">
              <input value={repoInput} onChange={(e) => setRepoInput(e.target.value)} placeholder="owner/repo" />
              <button className="icon-button" onClick={importRepo} disabled={busy === 'import'} aria-label="导入仓库">
                {busy === 'import' ? <LoaderCircle className="spin" size={17} /> : <Plus size={17} />}
              </button>
            </div>
            <div className="repo-list">
              {repositories.length === 0 && <div className="empty-mini">还没有索引仓库。<br />先导入一个公开 GitHub 项目。</div>}
              {repositories.map((repo) => (
                <button key={repo.full_name} className={`repo-item ${selected === repo.full_name ? 'active' : ''}`} onClick={() => setSelected(repo.full_name)}>
                  <span className="repo-name">{repo.full_name}</span>
                  <span>{repo.document_count} 条证据</span>
                </button>
              ))}
            </div>
            {selectedRepo && (
              <div className="repo-detail">
                <span>当前索引</span>
                <strong>{selectedRepo.document_count}</strong>
                <small>{selectedRepo.metadata.language || 'Unknown'} · ★ {selectedRepo.metadata.stargazers_count ?? 0}</small>
              </div>
            )}
          </aside>

          <section className="main-panel panel">
            <div className="panel-title"><ShieldCheck size={17} /> 发起调查</div>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="例如：升级后登录偶发 401，历史上有没有类似问题？当时是怎么修的？"
            />
            <div className="query-actions">
              <span>{selected ? `在 ${selected} 中调查` : '请先选择仓库'}</span>
              <button className="primary-button" onClick={investigate} disabled={!selected || !question.trim() || busy === 'investigate'}>
                {busy === 'investigate' ? <LoaderCircle className="spin" size={17} /> : <Search size={17} />} 开始调查
              </button>
            </div>
            {error && <div className="error-box">{error}</div>}

            {!result && <EmptyState />}
            {result && <InvestigationView result={result} />}
          </section>
        </section>

        {evaluation && <EvaluationPanel evaluation={evaluation} />}
      </main>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Search size={24} /></div>
      <h3>从一个真实故障开始</h3>
      <p>错误码、函数名、异常栈和“什么时候开始出现”都很有用。RepoTrace 会优先找历史 Issue 和已合并 PR，再把证据交给回答阶段。</p>
    </div>
  )
}

function InvestigationView({ result }: { result: Investigation }) {
  return (
    <div className="result-wrap">
      <div className="result-head">
        <div>
          <span className={`confidence ${result.confidence}`}>置信度 {result.confidence}</span>
          <span className="mode-badge">{result.used_llm ? 'LLM 综合' : '证据摘要模式'}</span>
        </div>
        <span>{result.evidence.length} 条核心证据</span>
      </div>
      <article className="answer-card"><pre>{result.answer}</pre></article>
      <div className="section-label">证据链</div>
      <div className="evidence-list">
        {result.evidence.map((evidence, index) => <EvidenceCard key={evidence.id} evidence={evidence} index={index + 1} />)}
      </div>
      <div className="section-label">执行链路</div>
      <div className="trace-row">
        {result.trace.map((step) => (
          <div className="trace-step" key={step.name}>
            <CheckCircle2 size={15} />
            <div><strong>{step.name}</strong><span>{step.duration_ms} ms</span></div>
          </div>
        ))}
      </div>
    </div>
  )
}

function EvidenceCard({ evidence, index }: { evidence: Evidence; index: number }) {
  const Icon = kindIcon[evidence.kind]
  return (
    <a className="evidence-card" href={evidence.url} target="_blank" rel="noreferrer">
      <div className="evidence-icon"><Icon size={16} /></div>
      <div className="evidence-body">
        <div className="evidence-meta"><span>[E{index}] {kindLabel[evidence.kind]}</span><span>score {evidence.score.toFixed(3)}</span></div>
        <strong>{evidence.title}</strong>
        <p>{evidence.excerpt || '无正文摘要'}</p>
        {evidence.reasons.length > 0 && <div className="reason-row">{evidence.reasons.map((reason) => <span key={reason}>{reason}</span>)}</div>}
      </div>
      <ArrowUpRight size={16} />
    </a>
  )
}

function EvaluationPanel({ evaluation }: { evaluation: Evaluation }) {
  return (
    <section className="evaluation panel">
      <div className="evaluation-title">
        <div><span className="eyebrow">Retrieval evaluation</span><h2>每次优化都要能被重新测出来。</h2></div>
        <p>{evaluation.note}</p>
      </div>
      <div className="eval-table">
        <div className="eval-row header"><span>检索方案</span><span>Hit Rate@5</span><span>MRR</span></div>
        {evaluation.variants.map((variant) => (
          <div className="eval-row" key={variant.id}>
            <strong>{variant.label}</strong><span>{(variant['hit_rate@5'] * 100).toFixed(1)}%</span><span>{variant.mrr.toFixed(3)}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
