import { useState } from 'react'
import { motion } from 'framer-motion'
import { toast } from 'react-hot-toast'
import UserMenu from './UserMenu'

const SAMPLE_REPOS = [
  { name: 'fastapi', url: 'https://github.com/tiangolo/fastapi' },
  { name: 'flask', url: 'https://github.com/pallets/flask' },
  { name: 'express', url: 'https://github.com/expressjs/express' },
  { name: 'react', url: 'https://github.com/facebook/react' },
]

const FEATURES = [
  { icon: '🌳', title: 'File Explorer', desc: 'VS Code–style tree navigation across any repo.' },
  { icon: '🔗', title: 'Dependency Graph', desc: 'Interactive force-directed import graph.' },
  { icon: '🧠', title: 'AI Deep Dive', desc: 'Groq-powered explanations for any file.' },
  { icon: '⚡', title: '60s Summary', desc: 'Elevator pitch, strengths & complexity score.' },
  { icon: '🛡️', title: 'Risk Radar', desc: 'Scans for secrets, XSS & injection patterns.' },
  { icon: '📄', title: 'README Studio', desc: 'Generate a polished README from architecture.' },
]

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.1 },
  },
}

const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] } },
}

const featuresVariant = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.04, delayChildren: 0.3 },
  },
}

const featureItem = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
}

export default function Hero({ onAnalyze, loading }) {
  const [url, setUrl] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    const trimmed = url.trim()
    if (!trimmed) {
      toast.error('Enter a repository URL')
      return
    }
    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
      toast.error('URL must start with https://')
      return
    }
    onAnalyze(trimmed)
  }

  return (
    <div className="hero-shell">
      {/* ── Top navigation bar ─────────────────────────────────── */}
      <nav className="hero-nav">
        <div className="wordmark">
          <div className="wordmark-icon" aria-hidden>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="2.5" fill="white" opacity="0.9"/>
              <path d="M7 1.5C4 1.5 1.5 4 1.5 7" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
              <path d="M7 12.5C10 12.5 12.5 10 12.5 7" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
              <path d="M1.5 7C1.5 10 4 12.5 7 12.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.25"/>
              <path d="M12.5 7C12.5 4 10 1.5 7 1.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.25"/>
            </svg>
          </div>
          <span className="wordmark-text">CodeScope <span>AI</span></span>
        </div>

        <div className="hero-nav-links">
          <span className="hero-nav-badge">
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e', display: 'inline-block' }} />
            Open Beta
          </span>
          <UserMenu />
        </div>
      </nav>

      {/* ── Main hero content ───────────────────────────────────── */}
      <div className="hero-content">
        <motion.div
          className="hero-inner"
          variants={container}
          initial="hidden"
          animate="show"
        >
          {/* Eyebrow */}
          <motion.div variants={item} style={{ display: 'flex', justifyContent: 'center', marginBottom: 28 }}>
            <span className="hero-eyebrow">
              AI-powered codebase exploration
            </span>
          </motion.div>

          {/* Headline */}
          <motion.h1 variants={item} className="hero-title">
            Understand any{' '}
            <span className="hero-title-accent">GitHub repo</span>
            {' '}in minutes
          </motion.h1>

          {/* Subtitle */}
          <motion.p variants={item} className="hero-subtitle">
            Paste a URL. We clone it, map dependencies, scan for risks,
            and give you an AI-powered walkthrough — zero config.
          </motion.p>

          {/* Input form */}
          <motion.form variants={item} className="hero-form" onSubmit={handleSubmit}>
            <div className="hero-input-row">
              {/* GitHub icon */}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0, opacity: 0.4 }}>
                <path
                  d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"
                  fill="currentColor"
                  style={{ color: 'var(--text-muted)' }}
                />
              </svg>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/owner/repository"
                autoComplete="url"
                spellCheck={false}
                style={{ fontSize: 14 }}
              />
              <motion.button
                type="submit"
                disabled={loading || !url.trim()}
                className="hero-btn-analyze"
                whileHover={{ scale: loading ? 1 : 1.02 }}
                whileTap={{ scale: loading ? 1 : 0.98 }}
              >
                {loading ? (
                  <span className="hero-loading-icon" aria-label="Loading">↻</span>
                ) : (
                  <>Analyze <span style={{ opacity: 0.7 }}>→</span></>
                )}
              </motion.button>
            </div>
          </motion.form>

          {/* Sample repos */}
          <motion.div variants={item} className="hero-samples">
            <span className="hero-sample-label">Try</span>
            {SAMPLE_REPOS.map((repo) => (
              <button
                key={repo.name}
                type="button"
                className="hero-sample-chip"
                onClick={() => {
                  setUrl(repo.url)
                  onAnalyze(repo.url)
                }}
              >
                {repo.name}
              </button>
            ))}
          </motion.div>

          {/* Feature grid */}
          <motion.div
            className="hero-features"
            variants={featuresVariant}
          >
            {FEATURES.map((f) => (
              <motion.div
                key={f.title}
                variants={featureItem}
                className="hero-feature-item"
              >
                <div className="hero-feature-icon">{f.icon}</div>
                <div className="hero-feature-text">
                  <h4>{f.title}</h4>
                  <p>{f.desc}</p>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </motion.div>
      </div>
    </div>
  )
}
