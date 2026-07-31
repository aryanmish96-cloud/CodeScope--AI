import { API_KEY_SETUP_STEPS } from '../utils/apiKeyError'

export default function ApiKeySetupCallout({ message }) {
  return (
    <div style={{
      padding: '10px 12px',
      borderRadius: 10,
      background: 'rgba(239,68,68,0.1)',
      border: '1px solid rgba(239,68,68,0.35)',
      fontSize: 12,
      lineHeight: 1.6,
      color: 'var(--text-secondary)',
    }}>
      <div style={{ fontWeight: 700, color: '#fca5a5', marginBottom: 6 }}>
        🔑 Groq API key required
      </div>
      {message && (
        <p style={{ margin: '0 0 8px' }}>{message}</p>
      )}
      <ol style={{ margin: 0, paddingLeft: 18 }}>
        {API_KEY_SETUP_STEPS.map((step) => (
          <li key={step} style={{ marginBottom: 4 }}>{step}</li>
        ))}
      </ol>
    </div>
  )
}
