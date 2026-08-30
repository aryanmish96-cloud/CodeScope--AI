import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'

function AvatarIcon({ email }) {
  const letter = email ? email[0].toUpperCase() : '?'
  return (
    <div className="user-avatar">
      {letter}
    </div>
  )
}

export default function UserMenu() {
  const { user, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const ref = useRef(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSignOut = async () => {
    setSigningOut(true)
    try {
      await signOut()
    } catch (err) {
      console.error('[signOut]', err)
    } finally {
      setSigningOut(false)
      setOpen(false)
    }
  }

  if (!user) return null

  return (
    <div className="user-menu-wrap" ref={ref}>
      <motion.button
        className="user-menu-trigger"
        onClick={() => setOpen(!open)}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        aria-label="User menu"
      >
        <AvatarIcon email={user.email} />
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="user-menu-dropdown"
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
          >
            {/* User info */}
            <div className="user-menu-info">
              <AvatarIcon email={user.email} />
              <div className="user-menu-details">
                <div className="user-menu-email">{user.email}</div>
                <div className="user-menu-badge">
                  <span className="user-status-dot" />
                  Active
                </div>
              </div>
            </div>

            <div className="user-menu-divider" />

            {/* Sign out */}
            <button
              className="user-menu-signout"
              onClick={handleSignOut}
              disabled={signingOut}
            >
              {signingOut ? (
                <span className="auth-spinner auth-spinner-sm" />
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                  <polyline points="16 17 21 12 16 7"/>
                  <line x1="21" y1="12" x2="9" y2="12"/>
                </svg>
              )}
              Sign Out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
