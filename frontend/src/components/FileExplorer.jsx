import { useState } from 'react'

// ── File type colors (dot indicators) ────────────────────────────────
const EXT_COLOR = {
  js:   '#f7df1e', jsx:  '#61dafb', ts:   '#3b82f6', tsx:  '#61dafb',
  py:   '#4b8bbe', java: '#ed8b00', go:   '#00add8', rs:   '#ce422b',
  css:  '#1572b6', scss: '#cd6799', html: '#e34f26',
  json: '#8bc34a', yaml: '#f29111', yml:  '#f29111',
  md:   '#94a3b8', sql:  '#f29111', vue:  '#42b883', svelte: '#ff3e00',
  sh:   '#10b981', dockerfile: '#0db7ed', toml: '#9b59b6',
}

const EXT_LABEL = {
  js: 'JS', jsx: 'JSX', ts: 'TS', tsx: 'TSX',
  py: 'PY', java: 'JAVA', go: 'GO', rs: 'RS',
  css: 'CSS', scss: 'SCSS', html: 'HTML',
  json: 'JSON', yaml: 'YML', yml: 'YML',
  md: 'MD', sql: 'SQL', vue: 'VUE', svelte: 'SVT',
  sh: 'SH', dockerfile: 'DOC', toml: 'TOML',
}

function ExtDot({ ext, size = 7 }) {
  const color = EXT_COLOR[ext] || '#555560'
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background: color,
        flexShrink: 0,
        display: 'inline-block',
      }}
      title={EXT_LABEL[ext] || ext?.toUpperCase()}
    />
  )
}

function ChevronIcon({ open }) {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 10 10"
      fill="none"
      style={{
        transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
        transition: 'transform 0.12s ease',
        color: 'var(--text-muted)',
        flexShrink: 0,
      }}
    >
      <path d="M3 2l4 3-4 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}

function FolderIcon({ open }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      {open ? (
        <path
          d="M1 4a1 1 0 0 1 1-1h4l2 2h6a1 1 0 0 1 1 1v1H1V4zm0 4h14l-1.5 5.5a1 1 0 0 1-.97.75H3.47a1 1 0 0 1-.97-.75L1 8z"
          fill="#818cf8" opacity="0.7"
        />
      ) : (
        <path
          d="M1 4a1 1 0 0 1 1-1h4l2 2h6a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V4z"
          fill="#555560"
        />
      )}
    </svg>
  )
}

function FileIcon({ ext }) {
  return (
    <svg width="13" height="14" viewBox="0 0 13 14" fill="none" style={{ flexShrink: 0 }}>
      <path
        d="M2 1h6.5L11 3.5V13a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1z"
        fill="var(--bg-elevated)"
        stroke="var(--border-strong)"
        strokeWidth="1"
      />
      <path d="M8.5 1v2.5H11" stroke="var(--border-strong)" strokeWidth="1" fill="none"/>
      {ext && EXT_COLOR[ext] && (
        <rect x="2" y="8" width="9" height="2" rx="1" fill={EXT_COLOR[ext]} opacity="0.6"/>
      )}
    </svg>
  )
}

function TreeNode({ node, depth = 0, onSelect, selectedPath }) {
  const [open, setOpen] = useState(depth < 2)
  const isFolder = node.type === 'folder'
  const isSelected = node.path === selectedPath

  return (
    <div>
      <div
        className={`file-tree-item ${isSelected ? 'selected' : ''}`}
        style={{ paddingLeft: `${10 + depth * 14}px`, gap: 6 }}
        onClick={() => {
          if (isFolder) setOpen(!open)
          else onSelect(node)
        }}
      >
        {isFolder ? (
          <>
            <ChevronIcon open={open} />
            <FolderIcon open={open} />
            <span
              style={{
                fontSize: 12.5,
                fontWeight: 500,
                color: 'var(--text-secondary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: 1,
              }}
            >
              {node.name}
            </span>
          </>
        ) : (
          <>
            <span style={{ width: 10, flexShrink: 0 }} />
            <FileIcon ext={node.extension} />
            <span
              className="file-name"
              style={{
                fontSize: 12.5,
                color: isSelected ? 'var(--text-accent)' : 'var(--text-secondary)',
                fontFamily: 'var(--font-mono)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: 1,
              }}
            >
              {node.name}
            </span>
            {!isFolder && node.lines > 0 && (
              <span
                style={{
                  fontSize: 10,
                  color: 'var(--text-faint)',
                  flexShrink: 0,
                  paddingRight: 8,
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {node.lines}
              </span>
            )}
          </>
        )}
      </div>
      {isFolder && open && node.children?.map((child, i) => (
        <TreeNode
          key={child.id || i}
          node={child}
          depth={depth + 1}
          onSelect={onSelect}
          selectedPath={selectedPath}
        />
      ))}
    </div>
  )
}

export default function FileExplorer({ tree, onFileSelect, selectedPath, stats }) {
  const [search, setSearch] = useState('')

  if (!tree) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">📂</div>
        <div className="empty-state-title">No repository loaded</div>
        <div className="empty-state-desc">Analyze a repo to browse its files</div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* ── Panel header ──────────────────────────────────────── */}
      <div className="panel-section-header">
        <span className="panel-section-label">Explorer</span>
        {stats && (
          <div style={{ display: 'flex', gap: 6 }}>
            <span className="badge badge-purple" style={{ fontSize: 10, padding: '1px 6px' }}>
              {stats.file_count} files
            </span>
            <span className="badge badge-gray" style={{ fontSize: 10, padding: '1px 6px' }}>
              {stats.total_lines?.toLocaleString()} LOC
            </span>
          </div>
        )}
      </div>

      {/* ── Repo name + search ───────────────────────────────── */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
          fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', fontWeight: 500,
        }}>
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" fill="var(--text-muted)"/>
          </svg>
          {tree.name}
        </div>
        <div style={{ position: 'relative' }}>
          <svg
            width="12" height="12"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
            style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }}
          >
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            className="input-field"
            style={{ padding: '6px 10px 6px 28px', fontSize: 12 }}
            placeholder="Filter files..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* ── File tree ────────────────────────────────────────── */}
      <div style={{ overflowY: 'auto', flex: 1, padding: '6px 0' }}>
        <TreeNode
          node={tree}
          depth={0}
          onSelect={onFileSelect}
          selectedPath={selectedPath}
        />
      </div>
    </div>
  )
}
