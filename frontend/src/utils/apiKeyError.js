/** Detect Groq / GROQ_API_KEY configuration errors returned by the backend. */
export function isApiKeyError(message) {
  if (!message || typeof message !== 'string') return false
  const lower = message.toLowerCase()
  return (
    lower.includes('groq api key') ||
    lower.includes('groq_api_key') ||
    lower.includes('invalid api key') ||
    lower.includes('console.groq.com/keys')
  )
}

export const API_KEY_SETUP_STEPS = [
  'Get a free key at console.groq.com/keys',
  'Open backend/.env and set GROQ_API_KEY=your_key_here',
  'Restart the backend (python main.py)',
]
