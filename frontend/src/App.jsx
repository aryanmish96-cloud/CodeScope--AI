import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Toaster, toast } from 'react-hot-toast'

import Hero from './components/Hero'
import FileExplorer from './components/FileExplorer'
import DependencyGraph from './components/DependencyGraph'
import AIPanel from './components/AIPanel'
import Dashboard from './components/Dashboard'
import ChatAssistant from './components/ChatAssistant'
import ReadmeModal from './components/ReadmeModal'
import LoadingOverlay from './components/LoadingOverlay'
import CodeViewer from './components/CodeViewer'
import AuthPage from './components/AuthPage'
import UserMenu from './components/UserMenu'
import { AuthProvider, useAuth } from './context/AuthContext'

import { startAnalyzeRepo, getAnalyzeStatus, getAnalyzeResult, summarizeRepo, analyzeArchitecture } from './api/client'
import { generateCodeScopeReport } from './utils/generateReportPdf'

// ── View tabs for the center panel ──────────────────────────────────
const CENTER_TABS = [
  { id: 'graph',     label: 'Graph' },
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'code',      label: 'Code' },
]

// ── Logo SVG ─────────────────────────────────────────────────────────
function LogoIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="2.5" fill="white" opacity="0.9"/>
      <path d="M7 1.5C4 1.5 1.5 4 1.5 7" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
      <path d="M7 12.5C10 12.5 12.5 10 12.5 7" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
      <path d="M1.5 7C1.5 10 4 12.5 7 12.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.25"/>
      <path d="M12.5 7C12.5 4 10 1.5 7 1.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.25"/>
    </svg>
  )
}

// ── Inner app (requires auth) ────────────────────────────────────────
function AppInner() {
  const { user, loading: authLoading } = useAuth()

  if (authLoading) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-base)' }}>
        <span className="auth-spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
      </div>
    )
  }

  if (!user) {
    return <AuthPage />
  }

  return <AppShell />
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  )
}

function AppShell() {
  const [view, setView] = useState('hero') // hero | explorer
  const [loading, setLoading] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState('')
  const [centerTab, setCenterTab] = useState('graph')
  const [chatOpen, setChatOpen] = useState(false)
  const [readmeOpen, setReadmeOpen] = useState(false)

  // Data state
  const [sessionId, setSessionId] = useState(null)
  const [repoName, setRepoName] = useState('')
  const [tree, setTree] = useState(null)
  const [graphData, setGraphData] = useState(null)
  const [architecture, setArchitecture] = useState(null)
  const [stats, setStats] = useState(null)
  const [securityRisks, setSecurityRisks] = useState([])
  const [repoSummary, setRepoSummary] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [highlightRanges, setHighlightRanges] = useState([])

  const [aiArchitecture, setAiArchitecture] = useState(null)
  const [aiArchLoading, setAiArchLoading] = useState(false)
  const [reportLoading, setReportLoading] = useState(false)

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

  // ── Analyze repo ──────────────────────────────────────────────────
  const handleAnalyze = useCallback(async (url) => {
    setLoading(true)
    setLoadingMessage('Queued for analysis...')
    setView('hero')

    try {
      const started = await startAnalyzeRepo(url)
      const jobId = started?.job_id
      if (!jobId) throw new Error('Failed to start analysis job')

      let status = null
      for (let i = 0; i < 600; i += 1) {
        status = await getAnalyzeStatus(jobId)
        if (status?.message) setLoadingMessage(status.message)
        if (status?.status === 'done') break
        if (status?.status === 'error') {
          throw new Error(status.error || status.message || 'Analysis failed')
        }
        await sleep(1000)
      }
      if (!status || status.status !== 'done') {
        throw new Error('Analysis timed out. Try again.')
      }

      const data = await getAnalyzeResult(jobId)
      setSessionId(data.session_id)
      setRepoName(data.repo_name)
      setTree(data.tree)
      setGraphData(data.graph)
      setArchitecture(data.architecture)
      setStats(data.stats)
      setSecurityRisks(data.security_risks || [])
      setSelectedFile(null)
      setRepoSummary(null)
      setAiArchitecture(null)
      setView('explorer')
      toast.success(`${data.repo_name} analyzed successfully`, { duration: 3000 })

      if (import.meta.env.DEV) {
        console.log('[session] analyze success, session_id=', data.session_id)
      }
      setTimeout(() => {
        summarizeRepo(data.session_id)
          .then(setRepoSummary)
          .catch((err) => {
            console.error('[summarize]', err?.response?.status, err?.response?.data || err)
            const detail = err?.response?.data?.detail
            const msg = typeof detail === 'string' ? detail : 'AI summary failed'
            toast.error(msg, { duration: 4000 })
          })
      }, 500)
    } catch (err) {
      console.error(err)
      const msg = err?.response?.data?.detail || err.message || 'Analysis failed'
      toast.error(msg, { duration: 5000 })
      setView('hero')
    } finally {
      setLoading(false)
      setLoadingMessage('')
    }
  }, [])

  // ── File click from explorer tree or chat ─────────────────────────
  const handleFileSelect = useCallback((file, highlights = []) => {
    setSelectedFile(file)
    setHighlightRanges(highlights)
    if (highlights.length > 0) {
      setCenterTab('code')
    }
  }, [])

  // ── Graph node click → file select ────────────────────────────────
  const handleGraphNodeClick = useCallback((nodeData) => {
    setSelectedFile({ path: nodeData.path, name: nodeData.label, extension: nodeData.extension })
  }, [])

  // ── README generator ──────────────────────────────────────────────
  const handleGenerateReadme = () => {
    if (!sessionId) return
    setReadmeOpen(true)
  }

  const handleGenerateReport = async () => {
    if (!sessionId || !stats) {
      toast.error('Analyze a repository first')
      return
    }
    setChatOpen(false)
    setReportLoading(true)
    const t = toast.loading('Building PDF — capturing graph, dashboard, AI panel…')
    try {
      await generateCodeScopeReport({
        repoName,
        stats,
        architecture,
        graphMetrics: graphData?.metrics,
        securityRisks,
        repoSummary,
        selectedFile,
        setCenterTab,
        currentTab: centerTab,
      })
      toast.success('Report downloaded', { id: t })
    } catch (err) {
      console.error(err)
      toast.error(err?.message || 'Could not generate PDF', { id: t })
    } finally {
      setReportLoading(false)
    }
  }

  // ── Deep architecture ──────────────────────────────────────────────
  const handleAnalyzeArchitecture = async () => {
    if (!sessionId) return
    setAiArchLoading(true)
    try {
      const data = await analyzeArchitecture(sessionId)
      setAiArchitecture(data)
      toast.success('Architecture analyzed by AI')
    } catch (err) {
      console.error(err)
      toast.error('AI Architecture analysis failed')
    } finally {
      setAiArchLoading(false)
    }
  }

  return (
    <>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-strong)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
            borderRadius: 10,
            boxShadow: 'var(--shadow-xl)',
          },
        }}
      />

      <LoadingOverlay visible={loading} statusText={loadingMessage} />

      <AnimatePresence mode="wait">
        {view === 'hero' ? (
          <motion.div
            key="hero"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.15 } }}
            style={{ height: '100vh', overflow: 'auto' }}
          >
            <Hero onAnalyze={handleAnalyze} loading={loading} />
          </motion.div>
        ) : (
          <motion.div
            key="explorer"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="app-layout"
          >
            {/* ── Header ─────────────────────────────────────────── */}
            <header className="app-header">
              {/* Logo section */}
              <div className="header-logo-section">
                <motion.button
                  className="wordmark"
                  onClick={() => setView('hero')}
                  whileHover={{ opacity: 0.8 }}
                  whileTap={{ scale: 0.97 }}
                  style={{ background: 'none', border: 'none' }}
                >
                  <div className="wordmark-icon">
                    <LogoIcon size={14} />
                  </div>
                  <span className="wordmark-text">CodeScope <span>AI</span></span>
                </motion.button>
              </div>

              {/* Main section: repo info + tabs */}
              <div className="header-main-section">
                {/* Repo tag */}
                {repoName && (
                  <div className="repo-tag" style={{ marginRight: 16 }}>
                    <span className="repo-dot" />
                    {repoName}
                    {architecture?.project_type && (
                      <span className="badge badge-purple" style={{ marginLeft: 4, fontSize: 10 }}>
                        {architecture.project_type}
                      </span>
                    )}
                  </div>
                )}

                {/* Center tabs */}
                <div className="tab-bar" style={{ marginLeft: 8 }}>
                  {CENTER_TABS.map((tab) => (
                    <button
                      key={tab.id}
                      className={`tab-btn ${centerTab === tab.id ? 'active' : ''}`}
                      onClick={() => setCenterTab(tab.id)}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Actions section */}
              <div className="header-actions-section">
                <button
                  className={`btn-ghost ${chatOpen ? 'active' : ''}`}
                  onClick={() => setChatOpen(!chatOpen)}
                  style={{ fontSize: 13 }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                  Chat
                </button>
                <button
                  className="btn-ghost"
                  onClick={() => setView('hero')}
                  style={{ fontSize: 13 }}
                >
                  ← New
                </button>
                <UserMenu />
              </div>
            </header>

            {/* ── Left Panel: File Explorer ───────────────────────── */}
            <aside className="panel-left">
              <FileExplorer
                tree={tree}
                onFileSelect={handleFileSelect}
                selectedPath={selectedFile?.path}
                stats={stats}
              />
            </aside>

            {/* ── Center Panel: Graph / Dashboard / Code ───────────── */}
            <main className="panel-center">
              <AnimatePresence mode="wait">
                {centerTab === 'graph' ? (
                  <motion.div
                    key="graph"
                    id="report-capture-graph"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{ width: '100%', height: '100%' }}
                  >
                    <DependencyGraph
                      graphData={graphData}
                      sessionId={sessionId}
                      onNodeClick={handleGraphNodeClick}
                      metrics={graphData?.metrics}
                    />
                  </motion.div>
                ) : centerTab === 'code' ? (
                  <motion.div
                    key="code"
                    id="report-capture-code"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{ width: '100%', height: '100%' }}
                  >
                    <CodeViewer
                      sessionId={sessionId}
                      selectedFile={selectedFile}
                      highlights={highlightRanges}
                    />
                  </motion.div>
                ) : (
                  <motion.div
                    key="dash"
                    id="report-capture-dashboard"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{ width: '100%', height: '100%', overflowY: 'auto' }}
                  >
                    <Dashboard
                      stats={stats}
                      architecture={architecture}
                      graphMetrics={graphData?.metrics}
                      securityRisks={securityRisks}
                      onGenerateReadme={handleGenerateReadme}
                      onGenerateReport={handleGenerateReport}
                      reportLoading={reportLoading}
                      aiArchitecture={aiArchitecture}
                      aiArchLoading={aiArchLoading}
                      onAnalyzeArchitecture={handleAnalyzeArchitecture}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </main>

            {/* ── Right Panel: AI Explanation ─────────────────────── */}
            <aside className="panel-right">
              <AIPanel
                sessionId={sessionId}
                selectedFile={selectedFile}
                techStack={architecture?.tech_stack}
                repoSummary={repoSummary}
              />
            </aside>

            {/* ── Floating chat FAB ────────────────────────────────── */}
            <motion.button
              className={`fab-chat ${chatOpen ? 'open' : ''}`}
              onClick={() => setChatOpen(!chatOpen)}
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.94 }}
              aria-label="Toggle chat"
            >
              {chatOpen ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18"/>
                  <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
              )}
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Overlays ─────────────────────────────────────────────────── */}
      <ChatAssistant
        sessionId={sessionId}
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        onFileClick={handleFileSelect}
      />

      {readmeOpen && sessionId && (
        <ReadmeModal
          sessionId={sessionId}
          repoName={repoName}
          open={readmeOpen}
          onClose={() => setReadmeOpen(false)}
        />
      )}
    </>
  )
}
