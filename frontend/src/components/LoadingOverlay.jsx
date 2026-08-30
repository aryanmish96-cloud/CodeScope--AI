import { motion, AnimatePresence } from 'framer-motion'
import { useState, useEffect } from 'react'

const STEPS = [
  'Cloning repository...',
  'Parsing file structure...',
  'Extracting dependencies...',
  'Building dependency graph...',
  'Detecting architecture...',
  'Running security scan...',
  'Finalizing analysis...',
]

export default function LoadingOverlay({ visible, statusText = '' }) {
  const [stepIdx, setStepIdx] = useState(0)
  const [progress, setProgress] = useState(8)

  useEffect(() => {
    if (!visible) {
      setStepIdx(0)
      setProgress(8)
      return
    }
    const interval = setInterval(() => {
      setStepIdx((s) => {
        const next = (s + 1) % STEPS.length
        setProgress(Math.min(92, 8 + (next / STEPS.length) * 84))
        return next
      })
    }, 2200)
    return () => clearInterval(interval)
  }, [visible])

  const currentText = statusText || STEPS[stepIdx]

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.2 } }}
          className="loading-modal"
        >
          {/* Top progress bar */}
          <div className="loading-top-bar" style={{ position: 'fixed', top: 0, left: 0, right: 0 }}>
            <motion.div
              className="loading-top-bar-fill"
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
              style={{ position: 'absolute', top: 0, left: 0, height: '100%' }}
            />
          </div>

          {/* Modal box */}
          <div className="loading-box">
            {/* Wordmark */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 10, marginBottom: 24,
            }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: 'var(--accent)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <svg width="18" height="18" viewBox="0 0 14 14" fill="none">
                  <circle cx="7" cy="7" r="2.5" fill="white" opacity="0.9"/>
                  <path d="M7 1.5C4 1.5 1.5 4 1.5 7" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
                  <path d="M7 12.5C10 12.5 12.5 10 12.5 7" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
                  <path d="M1.5 7C1.5 10 4 12.5 7 12.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.25"/>
                  <path d="M12.5 7C12.5 4 10 1.5 7 1.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.25"/>
                </svg>
              </div>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
                  Analyzing Repository
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  This may take 30–90 seconds
                </div>
              </div>
            </div>

            {/* Progress bar */}
            <div style={{ marginBottom: 20 }}>
              <div className="progress-bar-track" style={{ height: 4, borderRadius: 2 }}>
                <motion.div
                  className="progress-bar-fill"
                  animate={{ width: `${progress}%` }}
                  transition={{ duration: 0.6, ease: 'easeOut' }}
                  style={{ height: '100%', borderRadius: 2 }}
                />
              </div>
              <div style={{
                display: 'flex', justifyContent: 'space-between',
                marginTop: 6, fontSize: 11, color: 'var(--text-muted)',
              }}>
                <span>{Math.round(progress)}%</span>
                <span>Step {stepIdx + 1} of {STEPS.length}</span>
              </div>
            </div>

            {/* Current step */}
            <AnimatePresence mode="wait">
              <motion.div
                key={currentText}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.25 }}
                style={{
                  fontSize: 13, color: 'var(--text-secondary)',
                  textAlign: 'center',
                  padding: '10px 16px',
                  background: 'var(--bg-elevated)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border)',
                  minHeight: 40,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  gap: 8,
                }}
              >
                {/* Animated spinner dot */}
                <span className="pulse-dot" style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: 'var(--accent)',
                  display: 'inline-block', flexShrink: 0,
                }} />
                {currentText}
              </motion.div>
            </AnimatePresence>

            {/* Step dots */}
            <div style={{ display: 'flex', justifyContent: 'center', gap: 6, marginTop: 18 }}>
              {STEPS.map((_, i) => (
                <motion.span
                  key={i}
                  animate={{
                    width: i === stepIdx ? 18 : 6,
                    background: i <= stepIdx ? 'var(--accent)' : 'var(--bg-hover)',
                  }}
                  transition={{ duration: 0.2 }}
                  style={{
                    height: 6, borderRadius: 3,
                    display: 'inline-block',
                  }}
                />
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
