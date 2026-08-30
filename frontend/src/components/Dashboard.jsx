import { motion, AnimatePresence } from 'framer-motion'
import MermaidGraph from './MermaidGraph'

const SEV_STYLE = {
  critical: { dot: '#ef4444', text: '#fca5a5', label: 'Critical' },
  high:     { dot: '#f97316', text: '#fdba74', label: 'High' },
  medium:   { dot: '#eab308', text: '#fde047', label: 'Medium' },
  low:      { dot: '#6b7280', text: '#9ca3af', label: 'Low' },
}

function SectionHeader({ children, action }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      marginBottom: 10,
    }}>
      <span className="section-label">{children}</span>
      {action}
    </div>
  )
}

function StatGrid({ items }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 1,
      background: 'var(--border)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
      marginBottom: 16,
    }}>
      {items.map(({ label, value, color }, i) => (
        <div
          key={i}
          style={{
            background: 'var(--bg-surface)',
            padding: '14px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          <div style={{ fontSize: 20, fontWeight: 700, color: color || 'var(--text-primary)', letterSpacing: '-0.03em', fontFamily: 'var(--font-sans)' }}>
            {value}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {label}
          </div>
        </div>
      ))}
    </div>
  )
}

function ArchitectureFlow({ steps }) {
  if (!steps?.length) return null
  return (
    <div className="arch-flow">
      {steps.map((step, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div className="arch-step">
            <span>{step.icon}</span>
            <span>{step.label}</span>
          </div>
          {i < steps.length - 1 && <span className="arch-arrow">›</span>}
        </div>
      ))}
    </div>
  )
}

export default function Dashboard({
  stats,
  architecture,
  graphMetrics,
  securityRisks,
  onGenerateReadme,
  onGenerateReport,
  reportLoading,
  aiArchitecture,
  aiArchLoading,
  onAnalyzeArchitecture,
}) {
  if (!stats || !architecture) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">📊</div>
        <div className="empty-state-title">No analysis yet</div>
        <div className="empty-state-desc">Analyze a repository to see its dashboard</div>
      </div>
    )
  }

  const riskCounts = securityRisks?.reduce((acc, r) => {
    acc[r.severity] = (acc[r.severity] || 0) + 1
    return acc
  }, {}) || {}

  const complexityLabel = graphMetrics?.avg_complexity >= 6 ? 'High' : graphMetrics?.avg_complexity >= 3 ? 'Med' : 'Low'
  const complexityColor = graphMetrics?.avg_complexity >= 6 ? '#ef4444' : graphMetrics?.avg_complexity >= 3 ? '#f97316' : '#22c55e'

  const projectIcon = architecture.project_type?.includes('Full') ? '🏗️'
    : architecture.project_type?.includes('Frontend') ? '🎨'
    : architecture.project_type?.includes('Backend') ? '⚙️' : '📦'

  return (
    <div style={{ overflowY: 'auto', height: '100%', padding: '16px 16px 80px' }}>

      {/* ── Project type banner ─────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 14px',
          borderRadius: 'var(--radius-lg)',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          marginBottom: 16,
        }}
      >
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
            Project Type
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
            {architecture.project_type}
          </div>
          {stats.git?.branch && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
              <span style={{ color: 'var(--text-accent)' }}>{stats.git.branch}</span>
              {stats.git.contributor_count > 0 && ` · ${stats.git.contributor_count} contributor${stats.git.contributor_count > 1 ? 's' : ''}`}
            </div>
          )}
        </div>
        <span style={{ fontSize: 28, opacity: 0.7 }}>{projectIcon}</span>
      </motion.div>

      {/* ── Key metrics ─────────────────────────────────────── */}
      <StatGrid items={[
        { label: 'Files',        value: stats.file_count?.toLocaleString(),           color: '#818cf8' },
        { label: 'Lines of Code',value: stats.total_lines?.toLocaleString(),           color: '#93c5fd' },
        { label: 'Dependencies', value: graphMetrics?.total_edges || 0,               color: '#86efac' },
        { label: 'Complexity',   value: complexityLabel,                               color: complexityColor },
      ]} />

      {/* ── Tech stack ──────────────────────────────────────── */}
      {architecture.tech_stack?.length > 0 && (
        <div className="metric-card" style={{ marginBottom: 12 }}>
          <SectionHeader>Tech Stack</SectionHeader>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {architecture.tech_stack.map((tech, i) => (
              <span key={i} className="badge badge-purple" style={{ fontFamily: 'var(--font-mono)' }}>
                {tech}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Databases ────────────────────────────────────────── */}
      {architecture.databases?.length > 0 && (
        <div className="metric-card" style={{ marginBottom: 12 }}>
          <SectionHeader>Databases</SectionHeader>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {architecture.databases.map((db, i) => (
              <span key={i} className="badge badge-blue">{db}</span>
            ))}
          </div>
        </div>
      )}

      {/* ── Architecture flow ────────────────────────────────── */}
      {architecture.architecture_flow?.length > 0 && (
        <div className="metric-card" style={{ marginBottom: 12 }}>
          <SectionHeader>Architecture Flow</SectionHeader>
          <ArchitectureFlow steps={architecture.architecture_flow} />
        </div>
      )}

      {/* ── AI Deep Architecture ─────────────────────────────── */}
      <div className="metric-card" style={{
        marginBottom: 12,
        borderColor: aiArchitecture ? 'var(--accent-border)' : 'var(--border)',
      }}>
        <SectionHeader
          action={
            !aiArchitecture && (
              <button
                onClick={onAnalyzeArchitecture}
                disabled={aiArchLoading}
                className="btn-ghost"
                style={{ fontSize: 11, padding: '3px 10px', height: 'auto' }}
              >
                {aiArchLoading ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ display: 'inline-block', animation: 'spin 0.8s linear infinite', fontSize: 12 }}>↻</span>
                    Analyzing...
                  </span>
                ) : '✦ Run AI Analysis'}
              </button>
            )
          }
        >
          AI Architecture
        </SectionHeader>

        {!aiArchitecture && !aiArchLoading && (
          <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
            Run Groq AI analysis for a deep architecture breakdown with evidence-backed component detection.
          </p>
        )}

        {aiArchitecture && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65, margin: 0 }}>
              {aiArchitecture.explanation}
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 4 }}>
              {[
                { key: 'frontend', label: 'Frontend', value: aiArchitecture.frontend, color: '#93c5fd', evidenceKey: 'frontend' },
                { key: 'backend',  label: 'Backend',  value: aiArchitecture.backend,  color: '#a78bfa', evidenceKey: 'backend' },
                { key: 'database', label: 'Database', value: aiArchitecture.database, color: '#86efac', evidenceKey: 'database' },
                { key: 'apis',     label: 'API Routes', value: aiArchitecture.apis?.length > 0 ? aiArchitecture.apis.join(', ') : null, color: '#fca5a5', evidenceKey: null },
              ].map(({ key, label, value, color, evidenceKey }) => {
                const isDetected = value && value !== 'Not detected'
                const layerEvidence = evidenceKey && aiArchitecture.layer_evidence?.[evidenceKey]
                const evidenceCount = Array.isArray(layerEvidence) ? layerEvidence.length : 0
                return (
                  <div key={key} style={{
                    padding: '10px 12px',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border)',
                    opacity: isDetected ? 1 : 0.5,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                      <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-muted)' }}>
                        {label}
                      </div>
                      {evidenceCount > 0 && (
                        <span className="badge badge-green" style={{ fontSize: 9, padding: '1px 5px' }}>
                          {evidenceCount}
                        </span>
                      )}
                    </div>
                    <div style={{
                      fontWeight: 600, fontSize: isDetected ? 13 : 11,
                      color: isDetected ? color : 'var(--text-muted)',
                      fontStyle: isDetected ? 'normal' : 'italic',
                    }}>
                      {isDetected ? value : '— Not detected'}
                    </div>
                    {Array.isArray(layerEvidence) && layerEvidence.length > 0 && (
                      <div style={{ marginTop: 4, fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {layerEvidence.slice(0, 2).map((ev, ei) => (
                          <div key={ei} style={{ marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            ✓ {ev.file?.split('/').pop()}{ev.line ? `:${ev.line}` : ''}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {aiArchitecture.mermaid_diagram && (
              <div style={{ marginTop: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <span className="section-label">Verified Diagram</span>
                  <span className="badge badge-green" style={{ fontSize: 9 }}>Grounded</span>
                </div>
                <MermaidGraph chart={aiArchitecture.mermaid_diagram} />
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Key files ────────────────────────────────────────── */}
      {graphMetrics?.important_files?.length > 0 && (
        <div className="metric-card" style={{ marginBottom: 12 }}>
          <SectionHeader>Key Files</SectionHeader>
          <div>
            {graphMetrics.important_files.map((f, i) => (
              <div key={i} className="stat-row">
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11.5,
                  color: 'var(--text-secondary)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '75%',
                }}>
                  {f.path}
                </span>
                <span className="badge badge-orange" style={{ fontSize: 9, flexShrink: 0 }}>
                  cx {f.complexity}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Circular dependencies ────────────────────────────── */}
      {graphMetrics?.circular_dependency_count > 0 && (
        <div className="metric-card" style={{ marginBottom: 12, borderColor: 'rgba(239,68,68,0.25)' }}>
          <SectionHeader>
            Circular Dependencies
            <span className="badge badge-red" style={{ fontSize: 10 }}>{graphMetrics.circular_dependency_count}</span>
          </SectionHeader>
          {graphMetrics.circular_dependencies?.slice(0, 3).map((cycle, i) => (
            <div key={i} style={{
              fontSize: 11, color: 'var(--text-muted)',
              fontFamily: 'var(--font-mono)',
              padding: '3px 0',
              borderBottom: i < 2 ? '1px solid var(--border)' : 'none',
            }}>
              {cycle.join(' → ')}
            </div>
          ))}
        </div>
      )}

      {/* ── Security risks ───────────────────────────────────── */}
      {securityRisks?.length > 0 && (
        <div className="metric-card" style={{ marginBottom: 12 }}>
          <SectionHeader
            action={
              <div style={{ display: 'flex', gap: 4 }}>
                {Object.entries(riskCounts).map(([sev, count]) => (
                  <span
                    key={sev}
                    className={`badge badge-${sev === 'critical' || sev === 'high' ? 'red' : sev === 'medium' ? 'yellow' : 'gray'}`}
                    style={{ fontSize: 10 }}
                  >
                    {count} {sev}
                  </span>
                ))}
              </div>
            }
          >
            Risk Radar
          </SectionHeader>
          <div>
            {securityRisks.slice(0, 6).map((risk, i) => {
              const s = SEV_STYLE[risk.severity] || SEV_STYLE.low
              return (
                <div key={i} className="risk-row">
                  <span className="risk-dot" style={{ background: s.dot, marginTop: 5 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
                      {risk.risk}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      {risk.file} · {risk.occurrences}×
                    </div>
                  </div>
                  <span style={{ fontSize: 10, fontWeight: 700, color: s.text, flexShrink: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {risk.severity}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Actions (fixed bottom strip) ─────────────────────── */}
      <div style={{
        position: 'sticky',
        bottom: -80,
        margin: '0 -16px -80px',
        padding: '12px 16px',
        background: 'var(--bg-canvas)',
        borderTop: '1px solid var(--border)',
        display: 'flex',
        gap: 8,
      }}>
        <button
          onClick={onGenerateReport}
          disabled={reportLoading}
          className="btn-ghost"
          style={{ flex: 1, justifyContent: 'center', fontSize: 12 }}
        >
          {reportLoading ? '⏳ Building…' : '📑 PDF Report'}
        </button>
        <button
          onClick={onGenerateReadme}
          className="btn-primary"
          style={{ flex: 1, justifyContent: 'center', fontSize: 12 }}
        >
          📄 README
        </button>
      </div>
    </div>
  )
}
