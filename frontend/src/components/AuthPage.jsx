import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'

function LogoIcon({ size = 28 }) {
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

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  )
}

export default function AuthPage() {
  const { signIn, signUp, signInWithGoogle } = useAuth()
  const [tab, setTab] = useState('signin') // 'signin' | 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const reset = () => { setError(''); setSuccess('') }

  const handleSubmit = async (e) => {
    e.preventDefault()
    reset()

    if (tab === 'signup' && password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters')
      return
    }

    setLoading(true)
    try {
      if (tab === 'signin') {
        await signIn(email, password)
      } else {
        await signUp(email, password)
        setSuccess('Check your email to confirm your account!')
      }
    } catch (err) {
      setError(err.message || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogle = async () => {
    setGoogleLoading(true)
    reset()
    try {
      await signInWithGoogle()
    } catch (err) {
      setError(err.message || 'Google sign-in failed')
      setGoogleLoading(false)
    }
  }

  return (
    <div className="auth-page">
      {/* Animated background blobs */}
      <div className="auth-bg-blob auth-bg-blob-1" />
      <div className="auth-bg-blob auth-bg-blob-2" />
      <div className="auth-bg-blob auth-bg-blob-3" />

      <motion.div
        className="auth-card"
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      >
        {/* Logo + branding */}
        <div className="auth-brand">
          <div className="auth-logo-ring">
            <LogoIcon size={22} />
          </div>
          <div>
            <div className="auth-brand-name">CodeScope <span>AI</span></div>
            <div className="auth-brand-tagline">Intelligent Codebase Explorer</div>
          </div>
        </div>

        {/* Tab switcher */}
        <div className="auth-tabs">
          {['signin', 'signup'].map((t) => (
            <button
              key={t}
              className={`auth-tab-btn ${tab === t ? 'active' : ''}`}
              onClick={() => { setTab(t); reset() }}
            >
              {t === 'signin' ? 'Sign In' : 'Sign Up'}
            </button>
          ))}
        </div>

        <AnimatePresence mode="wait">
          <motion.form
            key={tab}
            onSubmit={handleSubmit}
            className="auth-form"
            initial={{ opacity: 0, x: tab === 'signin' ? -12 : 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: tab === 'signin' ? 12 : -12 }}
            transition={{ duration: 0.2 }}
          >
            {/* Error / success banners */}
            <AnimatePresence>
              {error && (
                <motion.div
                  className="auth-banner auth-banner-error"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  {error}
                </motion.div>
              )}
              {success && (
                <motion.div
                  className="auth-banner auth-banner-success"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg>
                  {success}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Email field */}
            <div className="auth-field">
              <label className="auth-label" htmlFor="auth-email">Email</label>
              <div className="auth-input-wrap">
                <svg className="auth-input-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
                <input
                  id="auth-email"
                  className="auth-input"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                />
              </div>
            </div>

            {/* Password field */}
            <div className="auth-field">
              <label className="auth-label" htmlFor="auth-password">Password</label>
              <div className="auth-input-wrap">
                <svg className="auth-input-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                <input
                  id="auth-password"
                  className="auth-input"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete={tab === 'signup' ? 'new-password' : 'current-password'}
                />
              </div>
            </div>

            {/* Confirm password (signup only) */}
            {tab === 'signup' && (
              <div className="auth-field">
                <label className="auth-label" htmlFor="auth-confirm">Confirm Password</label>
                <div className="auth-input-wrap">
                  <svg className="auth-input-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                  <input
                    id="auth-confirm"
                    className="auth-input"
                    type="password"
                    placeholder="••••••••"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                  />
                </div>
              </div>
            )}

            {/* Submit button */}
            <motion.button
              type="submit"
              className="auth-submit-btn"
              disabled={loading}
              whileHover={{ scale: loading ? 1 : 1.02 }}
              whileTap={{ scale: loading ? 1 : 0.98 }}
            >
              {loading ? (
                <span className="auth-spinner" />
              ) : (
                tab === 'signin' ? 'Sign In' : 'Create Account'
              )}
            </motion.button>

            {/* Divider */}
            <div className="auth-divider">
              <span>or continue with</span>
            </div>

            {/* Google OAuth */}
            <motion.button
              type="button"
              className="auth-google-btn"
              onClick={handleGoogle}
              disabled={googleLoading}
              whileHover={{ scale: googleLoading ? 1 : 1.02 }}
              whileTap={{ scale: googleLoading ? 1 : 0.98 }}
            >
              {googleLoading ? <span className="auth-spinner auth-spinner-dark" /> : <GoogleIcon />}
              Continue with Google
            </motion.button>

            {/* Switch tab link */}
            <p className="auth-switch">
              {tab === 'signin' ? "Don't have an account? " : 'Already have an account? '}
              <button type="button" className="auth-switch-link" onClick={() => { setTab(tab === 'signin' ? 'signup' : 'signin'); reset() }}>
                {tab === 'signin' ? 'Sign Up' : 'Sign In'}
              </button>
            </p>
          </motion.form>
        </AnimatePresence>
      </motion.div>
    </div>
  )
}
