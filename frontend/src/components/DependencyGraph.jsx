import React, { useCallback, useMemo, useEffect, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Handle,
  Position,
  useReactFlow,
  ReactFlowProvider
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { motion } from 'framer-motion'
import dagre from 'dagre'
import { getGraphOverview, getGraphNodeChildren, getGraphNodeDependencies } from '../api/client'
import { toast } from 'react-hot-toast'

// ── Dagre Layout Helper ──────────────────────────────────────────────
const getLayoutedElements = (nodes, edges, direction = 'LR') => {
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))
  
  // Approximate sizes
  const nodeWidth = 180
  const nodeHeight = 70
  
  dagreGraph.setGraph({ rankdir: direction, nodesep: 60, ranksep: 100 })
  
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight })
  })
  
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })
  
  dagre.layout(dagreGraph)
  
  return nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id)
    return {
      ...node,
      targetPosition: direction === 'LR' ? Position.Left : Position.Top,
      sourcePosition: direction === 'LR' ? Position.Right : Position.Bottom,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
    }
  })
}

// ── Custom Node ──────────────────────────────────────────────────────
function CodeNode({ data, selected, id }) {
  const getBorderColor = () => {
    if (data.isCircular) return '#ef4444'
    if (selected) return '#7c3aed'
    return 'rgba(255,255,255,0.1)'
  }

  const isModule = data.type === 'module'
  const isRepo = data.type === 'repository'

  return (
    <div style={{
      background: 'rgba(17,24,39,0.95)',
      border: `1.5px solid ${getBorderColor()}`,
      borderRadius: 10,
      padding: '8px 12px',
      minWidth: 150,
      maxWidth: 220,
      boxShadow: selected
        ? '0 0 20px rgba(124,58,237,0.5)'
        : '0 4px 12px rgba(0,0,0,0.5)',
      cursor: 'pointer',
      transition: 'all 0.2s ease',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: data.color || '#6b7280', border: 'none', width: 6, height: 6 }} />

      {/* Color stripe */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0,
        height: 3, borderRadius: '10px 10px 0 0',
        background: data.color || '#6b7280',
      }} />

      <div style={{ paddingTop: 4 }}>
        <div style={{
          fontSize: 11.5,
          fontFamily: 'var(--font-mono)',
          color: '#e2e8f0',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: 6
        }}>
          {isRepo ? '📁' : isModule ? '📦' : '📄'} {data.label}
        </div>
        
        {isModule && (
          <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 4 }}>
            Files: {data.file_count || 0}
            <button 
              onClick={(e) => {
                e.stopPropagation();
                data.onExpand(id, data.isExpanded);
              }}
              style={{ marginLeft: 8, padding: '2px 6px', fontSize: 9, background: '#374151', borderRadius: 4, color: 'white', border: 'none', cursor: 'pointer' }}
            >
              {data.isExpanded ? 'Collapse' : 'Expand'}
            </button>
          </div>
        )}

        {!isModule && !isRepo && (
          <div style={{ display: 'flex', gap: 6, marginTop: 4, alignItems: 'center' }}>
            <span style={{
              fontSize: 9, padding: '1px 5px', borderRadius: 3,
              background: `${data.color || '#6b7280'}22`, color: data.color || '#6b7280',
              fontFamily: 'var(--font-mono)',
            }}>
              .{data.extension || 'txt'}
            </span>
            {data.lines > 0 && (
              <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>
                {data.lines}L
              </span>
            )}
            <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>
              {data.category}
            </span>
          </div>
        )}
      </div>

      <Handle type="source" position={Position.Right} style={{ background: data.color || '#6b7280', border: 'none', width: 6, height: 6 }} />
    </div>
  )
}

const nodeTypes = { codeNode: CodeNode }

// ── Inner Component with useReactFlow ────────────────────────────────
function GraphInner({ sessionId, onNodeClick, initialMetrics }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const { fitView, getNodes, getEdges } = useReactFlow()
  const [loading, setLoading] = useState(false)
  
  // Transform backend nodes to ReactFlow nodes
  const transformNodes = useCallback((backendNodes, expandCallback) => {
    return backendNodes.map(n => ({
      id: n.id,
      type: 'codeNode',
      position: { x: 0, y: 0 },
      data: {
        label: n.label,
        type: n.type,
        parent_id: n.parent_id,
        isExpanded: false,
        ...n.data,
        onExpand: expandCallback,
      }
    }))
  }, [])

  const transformEdges = useCallback((backendEdges) => {
    return backendEdges.map(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      animated: e.type === 'IMPORTS',
      style: { stroke: e.type === 'CONTAINS' ? '#9ca3af' : '#6366f1', strokeWidth: e.type === 'CONTAINS' ? 1 : 1.5, strokeDasharray: e.type === 'CONTAINS' ? '4 4' : 'none' },
      markerEnd: { type: 'arrowclosed', color: e.type === 'CONTAINS' ? '#6b7280' : '#8b5cf6' },
      label: e.type === 'CONTAINS' ? '' : 'imports',
      labelStyle: { fill: '#9ca3af', fontSize: 10, fontWeight: 700 },
      labelBgStyle: { fill: '#1f2937', color: '#fff', fillOpacity: 0.8 },
      labelBgPadding: [4, 2],
      labelBgBorderRadius: 4,
    }))
  }, [])

  const handleToggleExpand = useCallback(async (nodeId, isCurrentlyExpanded) => {
    if (!sessionId) return
    try {
      setLoading(true)
      const currentNodes = getNodes()
      const currentEdges = getEdges()
      
      if (isCurrentlyExpanded) {
        // --- COLLAPSE ---
        const toRemove = new Set()
        const findDescendants = (pid) => {
          currentNodes.forEach(n => {
            if (n.data.parent_id === pid && !toRemove.has(n.id)) {
              toRemove.add(n.id)
              findDescendants(n.id)
            }
          })
        }
        findDescendants(nodeId)
        
        const nextNodes = currentNodes
          .filter(n => !toRemove.has(n.id))
          .map(n => n.id === nodeId ? { ...n, data: { ...n.data, isExpanded: false } } : n)
          
        const nextEdges = currentEdges.filter(e => !toRemove.has(e.source) && !toRemove.has(e.target))
        
        const layoutedNodes = getLayoutedElements(nextNodes, nextEdges)
        setNodes(layoutedNodes)
        setEdges(nextEdges)
        setTimeout(() => fitView({ duration: 800, padding: 0.2 }), 50)
      } else {
        // --- EXPAND ---
        const data = await getGraphNodeChildren(sessionId, nodeId)
        
        const existingIds = new Set(currentEdges.map(e => e.id))
        const newEdges = transformEdges(data.edges.filter(e => !existingIds.has(e.id)))
        const combinedEdges = [...currentEdges, ...newEdges]
        
        const existingNodeIds = new Set(currentNodes.map(n => n.id))
        const newNodes = transformNodes(data.nodes.filter(n => !existingNodeIds.has(n.id)), handleToggleExpand)
        
        const nextNodes = currentNodes.map(n => n.id === nodeId ? { ...n, data: { ...n.data, isExpanded: true } } : n)
        const combinedNodes = [...nextNodes, ...newNodes]
        
        const layoutedNodes = getLayoutedElements(combinedNodes, combinedEdges)
        
        setNodes(layoutedNodes)
        setEdges(combinedEdges)
        setTimeout(() => fitView({ duration: 800, padding: 0.2 }), 50)
      }
    } catch (err) {
      toast.error('Failed to toggle node')
    } finally {
      setLoading(false)
    }
  }, [sessionId, fitView, transformNodes, transformEdges, getNodes, getEdges])

  // Load Overview on mount
  useEffect(() => {
    if (!sessionId) return
    let mounted = true
    
    setLoading(true)
    getGraphOverview(sessionId).then(data => {
      if (!mounted) return
      
      const rfNodes = transformNodes(data.nodes, handleToggleExpand)
      const rfEdges = transformEdges(data.edges)
      
      const layoutedNodes = getLayoutedElements(rfNodes, rfEdges)
      setNodes(layoutedNodes)
      setEdges(rfEdges)
      
      setTimeout(() => fitView({ padding: 0.2 }), 50)
    }).catch(err => {
      if(mounted) toast.error('Failed to load graph overview')
    }).finally(() => {
      if(mounted) setLoading(false)
    })
    
    return () => { mounted = false }
  }, [sessionId]) // Intentionally omitting other deps to prevent infinite loop

  const handleNodeClick = useCallback((_, node) => {
    if (node.data.type === 'file') {
      onNodeClick?.({ path: node.data.path, name: node.data.label, extension: node.data.extension })
    }
  }, [onNodeClick])

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      {loading && (
        <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 10, color: 'white' }}>
          Loading graph...
        </div>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
      >
        <Background color="#1f2937" gap={24} size={1} />
        <Controls />
        <MiniMap
          nodeColor={(node) => node.data?.color || '#6b7280'}
          maskColor="rgba(8,11,20,0.8)"
        />
      </ReactFlow>

      {/* Metrics overlay */}
      {initialMetrics && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            position: 'absolute', top: 12, left: 12,
            display: 'flex', gap: 8, flexWrap: 'wrap',
            pointerEvents: 'none',
          }}
        >
          <div className="glass" style={{ padding: '6px 12px', borderRadius: 8, fontSize: 11 }}>
            <span style={{ color: 'var(--text-muted)' }}>Nodes (Total) </span>
            <span style={{ color: '#a78bfa', fontWeight: 600 }}>{initialMetrics.total_nodes}</span>
          </div>
          <div className="glass" style={{ padding: '6px 12px', borderRadius: 8, fontSize: 11 }}>
            <span style={{ color: 'var(--text-muted)' }}>Avg complexity </span>
            <span style={{ color: '#6ee7b7', fontWeight: 600 }}>{initialMetrics.avg_complexity}</span>
          </div>
        </motion.div>
      )}

      {/* Legend */}
      <div style={{
        position: 'absolute', top: 12, right: 12,
        padding: '8px 12px', borderRadius: 8, fontSize: 10,
        display: 'flex', flexDirection: 'column', gap: 4,
        backgroundColor: 'rgba(15, 23, 42, 0.85)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        backdropFilter: 'blur(4px)',
        zIndex: 10
      }}>
        <div style={{ color: 'var(--text-muted)', fontWeight: 600, marginBottom: 2 }}>EDGE TYPES</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 20, height: 2, background: '#6b7280', borderStyle: 'dashed' }} />
          <span style={{ color: 'var(--text-secondary)' }}>Contains (Module → File)</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 20, height: 2, background: '#8b5cf6' }} />
          <span style={{ color: 'var(--text-secondary)' }}>Imports (Dependency)</span>
        </div>
      </div>
    </div>
  )
}

// ── Main Export ──────────────────────────────────────────────────────
export default function DependencyGraph({ graphData, sessionId, onNodeClick, metrics }) {
  if (!sessionId) {
    return (
      <div style={{
        height: '100%', display: 'flex', alignItems: 'center',
        justifyContent: 'center', flexDirection: 'column', gap: 12,
        color: 'var(--text-muted)',
      }}>
        <span style={{ fontSize: 40 }}>🕸️</span>
        <span style={{ fontSize: 14 }}>No graph data yet</span>
        <span style={{ fontSize: 12 }}>Analyze a repository to see the dependency graph</span>
      </div>
    )
  }

  return (
    <ReactFlowProvider>
      <GraphInner sessionId={sessionId} onNodeClick={onNodeClick} initialMetrics={metrics} />
    </ReactFlowProvider>
  )
}
