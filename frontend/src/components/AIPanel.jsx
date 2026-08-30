import { motion, AnimatePresence } from 'framer-motion'
import { useState, useEffect } from 'react'
import { explainFile } from '../api/client'
import ExecutionSimulator from './ExecutionSimulator'

function ConfidenceBar({ value }) {
  const color = value >= 75 ? 'var(--green)' : value >= 50 ? 'var(--orange)' : 'var(--red)'
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5, fontSize: 11 }}>
        <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>AI Confidence</span>
        <span style={{ color, fontWeight: 600 }}>{value}%</span>
      </div>
      <div className="progress-bar-track">
        <motion.div
          className="progress-bar-fill"
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          style={{ background: color }}
        />
      </div>
    </div>
  )
}

function FileBreadcrumb({ path }) {
  if (!path) return null
  const parts = path.split('/')
  const file = parts.pop()
  return (
    <div className="breadcrumb">
      {parts.slice(-2).map((p, i) => (
        <span key={i} className="breadcrumb-part">
          {p}
          <span className="breadcrumb-sep"> / </span>
        </span>
      ))}
      <span className="breadcrumb-file">{file}</span>
    </div>
  )
}

const PANEL_TABS = [
  { id: 'explain',  label: 'File' },
  { id: 'flow',     label: 'Flow' },
  { id: 'summary',  label: 'Repo' },
  { id: 'security', label: 'Risks' },
]

export default function AIPanel({ sessionId, selectedFile, techStack, repoSummary }) {
  const [explanation, setExplanation] = useState(null)
  const [loading, setLoading] = useState(false)
  const [eli5, setEli5] = useState(false)
  const [tab, setTab] = useState('explain')

  useEffect(() => {
    if (!sessionId || !selectedFile?.path) {
      setExplanation(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setExplanation(null)

    ;(async () => {
      try {
        const data = await explainFile(sessionId, selectedFile.path, eli5)
        if (!cancelled) setExplanation(data)
      } catch (e) {
        const detail = e?.response?.data?.detail
        const errMsg =
          typeof detail === 'string'
            ? detail
            : Array.isArray(detail)
              ? detail.map((d) => d.msg || d).join(', ')
              : e.message || 'Unknown error'
        if (!cancelled) {
          setExplanation({ summary: `Error: ${errMsg}`, key_functions: [], confidence: 0 })
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [sessionId, selectedFile?.path, eli5])

  return (
    <div id="report-capture-aipanel" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* ── Panel header ──────────────────────────────────────── */}
      <div className="panel-section-header">
        <span className="panel-section-label">AI Explanation</span>
        <button
          onClick={() => setEli5(v => !v)}
          className={`btn-ghost ${eli5 ? 'active' : ''}`}
          style={{ fontSize: 11, padding: '2px 8px', height: 'auto', borderRadius: 'var(--radius-sm)' }}
        >
          ELI5
        </button>
      </div>

      {/* ── Tab bar ───────────────────────────────────────────── */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid var(--border)',
        padding: '0 8px',
        flexShrink: 0,
      }}>
        {PANEL_TABS.map(t => (
          <button
            key={t.id}
            className={`tab-btn ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
            style={{ fontSize: 12, padding: '0 10px', height: 36 }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Content ───────────────────────────────────────────── */}
      <div className="panel-body">
        <AnimatePresence mode="wait">

          {/* FILE EXPLAIN */}
          {tab === 'explain' && (
            <motion.div
              key="explain"
              initial={{ opacity: 0, x: 6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              transition={{ duration: 0.2 }}
            >
              {!selectedFile && (
                <div className="empty-state" style={{ height: 200 }}>
                  <div className="empty-state-icon" style={{ fontSize: 24 }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                      <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
                      <polyline points="13 2 13 9 20 9"/>
                    </svg>
                  </div>
                  <div className="empty-state-title">No file selected</div>
                  <div className="empty-state-desc">Click any file in the explorer or a graph node</div>
                </div>
              )}

              {loading && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
                  {[90, 70, 85, 55, 75].map((w, i) => (
                    <div key={i} className="shimmer" style={{ height: 11, width: `${w}%` }} />
                  ))}
                  <div style={{ height: 8 }} />
                  {[60, 80, 65].map((w, i) => (
                    <div key={i} className="shimmer" style={{ height: 11, width: `${w}%` }} />
                  ))}
                </div>
              )}

              {explanation && !loading && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
                >
                  {/* File path breadcrumb */}
                  {selectedFile && (
                    <div style={{
                      padding: '7px 10px',
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border)',
                    }}>
                      <FileBreadcrumb path={selectedFile.path} />
                    </div>
                  )}

                  {eli5 && <span className="badge badge-purple" style={{ alignSelf: 'flex-start' }}>ELI5 Mode</span>}

                  {/* Summary */}
                  <div>
                    <div className="section-label" style={{ marginBottom: 8 }}>Summary</div>
                    <p className="prose">{explanation.summary}</p>
                  </div>

                  {/* Key functions */}
                  {explanation.key_functions?.length > 0 && (
                    <div>
                      <div className="section-label" style={{ marginBottom: 8 }}>Key Functions</div>
                      <div>
                        {explanation.key_functions.map((fn, i) => (
                          <div key={i} className="fn-item">
                            <div className="fn-name">
                              {typeof fn === 'string' ? fn : fn.name}
                            </div>
                            {typeof fn !== 'string' && fn.description && (
                              <div className="fn-desc">{fn.description}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Logic flow */}
                  {explanation.logic_flow && (
                    <div>
                      <div className="section-label" style={{ marginBottom: 8 }}>Logic Flow</div>
                      <div style={{
                        padding: '10px 12px',
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--bg-base)',
                        border: '1px solid var(--border)',
                        fontSize: 12.5,
                        color: 'var(--text-secondary)',
                        lineHeight: 1.7,
                        fontFamily: 'var(--font-mono)',
                      }}>
                        {explanation.logic_flow}
                      </div>
                    </div>
                  )}

                  {/* Role in project */}
                  {explanation.role_in_project && (
                    <div>
                      <div className="section-label" style={{ marginBottom: 8 }}>Role in Project</div>
                      <div style={{
                        padding: '10px 12px',
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--accent-border)',
                        fontSize: 12.5,
                        color: 'var(--text-secondary)',
                        lineHeight: 1.7,
                      }}>
                        {explanation.role_in_project}
                      </div>
                    </div>
                  )}

                  {/* Security flags */}
                  {explanation.security_flags?.length > 0 && (
                    <div>
                      <div className="section-label" style={{ marginBottom: 8, color: 'var(--red)' }}>Security Flags</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {explanation.security_flags.map((flag, i) => (
                          <div key={i} style={{
                            display: 'flex', alignItems: 'flex-start', gap: 8,
                            padding: '6px 10px',
                            borderRadius: 'var(--radius-sm)',
                            background: 'var(--red-muted)',
                            border: '1px solid rgba(239,68,68,0.2)',
                          }}>
                            <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--red)', textTransform: 'uppercase', paddingTop: 2, flexShrink: 0 }}>
                              ⚠
                            </span>
                            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{flag}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Confidence */}
                  {explanation.confidence !== undefined && (
                    <ConfidenceBar value={explanation.confidence} />
                  )}
                </motion.div>
              )}
            </motion.div>
          )}

          {/* FLOW */}
          {tab === 'flow' && (
            <motion.div
              key="flow"
              initial={{ opacity: 0, x: 6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              transition={{ duration: 0.2 }}
            >
              <ExecutionSimulator sessionId={sessionId} selectedFile={selectedFile} />
            </motion.div>
          )}

          {/* REPO SUMMARY */}
          {tab === 'summary' && (
            <motion.div
              key="summary"
              initial={{ opacity: 0, x: 6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              transition={{ duration: 0.2 }}
            >
              {!repoSummary ? (
                <div className="empty-state" style={{ height: 180 }}>
                  <div className="empty-state-icon" style={{ fontSize: 20 }}>⏳</div>
                  <div className="empty-state-title">Summary loading…</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {repoSummary.elevator_pitch && (
                    <div style={{
                      padding: '12px 14px',
                      borderRadius: 'var(--radius-lg)',
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--accent-border)',
                    }}>
                      <p style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--text-primary)', lineHeight: 1.6, fontStyle: 'italic' }}>
                        "{repoSummary.elevator_pitch}"
                      </p>
                    </div>
                  )}
                  {repoSummary.detailed_summary && (
                    <div>
                      <div className="section-label" style={{ marginBottom: 8 }}>Overview</div>
                      <p className="prose">{repoSummary.detailed_summary}</p>
                    </div>
                  )}
                  {repoSummary.sixty_second_explanation && (
                    <div>
                      <div className="section-label" style={{ marginBottom: 8 }}>60-Second Pitch</div>
                      <p className="prose">{repoSummary.sixty_second_explanation}</p>
                    </div>
                  )}
                  {repoSummary.strengths?.length > 0 && (
                    <div>
                      <div className="section-label" style={{ marginBottom: 8, color: 'var(--green)' }}>Strengths</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {repoSummary.strengths.map((s, i) => (
                          <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                            <span style={{ color: 'var(--green)', fontWeight: 600, flexShrink: 0 }}>+</span>
                            <span>{s}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {repoSummary.weaknesses?.length > 0 && (
                    <div>
                      <div className="section-label" style={{ marginBottom: 8, color: 'var(--red)' }}>Weaknesses</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {repoSummary.weaknesses.map((w, i) => (
                          <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                            <span style={{ color: 'var(--red)', fontWeight: 600, flexShrink: 0 }}>−</span>
                            <span>{w}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {repoSummary.confidence !== undefined && (
                    <ConfidenceBar value={repoSummary.confidence} />
                  )}
                </div>
              )}
            </motion.div>
          )}

          {/* RISKS */}
          {tab === 'security' && (
            <motion.div
              key="security"
              initial={{ opacity: 0, x: 6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              transition={{ duration: 0.2 }}
            >
              <div className="empty-state" style={{ height: 180 }}>
                <div className="empty-state-icon" style={{ fontSize: 20 }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                  </svg>
                </div>
                <div className="empty-state-title">Security risks</div>
                <div className="empty-state-desc">View full risk breakdown in the Dashboard tab</div>
              </div>
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </div>
  )
}
