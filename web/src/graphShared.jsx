import dagre from '@dagrejs/dagre'
import { Handle, Position } from 'reactflow'

export const UNI_COLORS = {
  UdeM:      '#0057a8',
  UQAM:      '#00833e',
  McGill:    '#ed1b2f',
  Concordia: '#912338',
  Poly:      '#f0a500',
  ETS:       '#e63946',
}

const TAG_COLORS = [
  '#e8f0fe', '#e6f4ea', '#fff8e1', '#fce8e6', '#f3e8fd',
  '#e8f5e9', '#e3f2fd', '#fff3e0', '#fce4ec', '#e8eaf6',
  '#e0f7fa', '#f9fbe7',
]
const TAG_TEXT_COLORS = [
  '#1a47a8', '#1e7e34', '#8a6d00', '#c62828', '#6a1b9a',
  '#2e7d32', '#0d47a1', '#e65100', '#880e4f', '#283593',
  '#006064', '#558b2f',
]
const _tagIndex = {}
let _tagCounter = 0
export function tagStyle(tag) {
  if (_tagIndex[tag] == null) _tagIndex[tag] = _tagCounter++ % TAG_COLORS.length
  const i = _tagIndex[tag]
  return { background: TAG_COLORS[i], color: TAG_TEXT_COLORS[i] }
}

const EQUIVALENT_COLOR = '#8a3ffc'
const OFFICIAL_BADGE = { bg: '#e6f4ea', color: '#1e7e34' }
const INFERRED_BADGE = { bg: '#fff8e1', color: '#8a6d00' }

function equivalentBadgeLabel(data) {
  if (data.source === 'official') return `OFFICIELLE · ${data.universite}`
  return `SIMILAIRE ${Math.round((data.confidence ?? 0) * 100)}% · ${data.universite}`
}

export function CourseNode({ data }) {
  // Collapsed "Cours complétés" aggregate node
  if (data.isCollapsed) {
    return (
      <div style={{
        background: '#f0faf3',
        border: '2px solid #2a9d4e',
        borderRadius: 16,
        padding: '6px 16px',
        fontFamily: 'system-ui, sans-serif',
        cursor: 'default',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 2,
        boxShadow: '0 1px 4px rgba(42,157,78,.15)',
        minWidth: 130,
      }}>
        <Handle type="target" position={Position.Left} style={{ background: '#2a9d4e' }} />
        <div style={{ fontSize: 11, fontWeight: 700, color: '#2a9d4e', display: 'flex', alignItems: 'center', gap: 5 }}>
          <span>✓</span> Cours complétés
        </div>
        <div style={{ fontSize: 9.5, color: '#5a8a6a' }}>{data.titre}</div>
        <Handle type="source" position={Position.Right} style={{ background: '#2a9d4e' }} />
      </div>
    )
  }

  const isSub = !!data.substitution
  const displaySigle = isSub ? data.substitution.sigle : data.sigle
  const displayTitre = isSub ? data.substitution.titre : data.titre
  const displayUni   = isSub ? data.substitution.universite : data.universite

  const color = UNI_COLORS[displayUni] || '#999'
  const isEquivalent = !!data.is_equivalent

  const bg = data.completed ? '#f0faf3'
    : isSub ? '#f3f0ff'
    : data.isRoot ? '#f0f6ff'
    : isEquivalent ? '#faf5ff'
    : '#fff'
  const border = data.completed ? '#2a9d4e'
    : isSub ? '#7c5cbf'
    : data.isRoot ? '#1a6ef5'
    : isEquivalent ? EQUIVALENT_COLOR
    : '#ddd'
  const leftBorder = data.completed ? '#2a9d4e'
    : isSub ? color
    : isEquivalent ? EQUIVALENT_COLOR
    : color
  const borderStyle = isSub || (isEquivalent && !data.completed) ? 'dashed' : 'solid'

  return (
    <div style={{
      background: bg,
      border: `1.5px ${borderStyle} ${border}`,
      borderLeft: `4px solid ${leftBorder}`,
      borderRadius: 8,
      padding: '8px 12px',
      minWidth: 160,
      maxWidth: 200,
      boxShadow: data.isRoot ? '0 0 0 3px rgba(26,110,245,0.15)' : '0 1px 3px rgba(0,0,0,.08)',
      fontFamily: 'system-ui, sans-serif',
      cursor: 'pointer',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#aaa' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 4 }}>
        <div style={{ fontSize: 11, fontWeight: 700, fontFamily: 'monospace', color: '#333', marginBottom: 3 }}>
          {displaySigle}
          {data.completed && <span style={{ marginLeft: 6, color: '#2a9d4e', fontSize: 12 }}>✓</span>}
        </div>
        {data.isRoot && data.onRemoveChain && (
          <button
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ccc', fontSize: 13, padding: 0, lineHeight: 1, flexShrink: 0 }}
            onClick={e => { e.stopPropagation(); data.onRemoveChain(data.sigle) }}
            title="Retirer du graphe"
          >×</button>
        )}
      </div>

      {isSub && (
        <div style={{
          display: 'inline-block', fontSize: 9, fontWeight: 700, letterSpacing: '0.05em',
          marginBottom: 3, padding: '1px 6px', borderRadius: 4,
          background: '#ede9f8', color: '#7c5cbf',
        }}>
          via {displayUni}
        </div>
      )}

      {!isSub && isEquivalent && (
        <div style={{
          display: 'inline-block', fontSize: 9, fontWeight: 700, letterSpacing: '0.05em',
          marginBottom: 2, padding: '1px 6px', borderRadius: 4,
          background: data.source === 'official' ? OFFICIAL_BADGE.bg : INFERRED_BADGE.bg,
          color: data.source === 'official' ? OFFICIAL_BADGE.color : INFERRED_BADGE.color,
        }}>
          {equivalentBadgeLabel(data)}
        </div>
      )}

      <div style={{ fontSize: 11, color: '#555', lineHeight: 1.35 }}>
        {displayTitre ? displayTitre.slice(0, 45) + (displayTitre.length > 45 ? '…' : '') : ''}
      </div>

      {isSub && (
        <div style={{ fontSize: 9, color: '#aaa', marginTop: 2, fontFamily: 'monospace' }}>
          ({data.sigle})
        </div>
      )}

      {!isSub && data.tags && data.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 5 }}>
          {data.tags.slice(0, 2).map(tag => (
            <span key={tag} style={{
              ...tagStyle(tag), fontSize: 9, fontWeight: 700,
              padding: '1px 5px', borderRadius: 3, letterSpacing: '0.03em',
            }}>
              {tag}
            </span>
          ))}
          {data.tags.length > 2 && (
            <span style={{ fontSize: 9, color: '#aaa', alignSelf: 'center' }}>
              +{data.tags.length - 2}
            </span>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ background: '#aaa' }} />
    </div>
  )
}

export function GroupNode({ data }) {
  const isAnd = data.type === 'AND'
  return (
    <div style={{
      background: isAnd ? '#e8f0fe' : '#fff4e6',
      border: `1.5px solid ${isAnd ? '#4285f4' : '#f59f00'}`,
      borderRadius: 20,
      padding: '4px 12px',
      fontSize: 11,
      fontWeight: 700,
      color: isAnd ? '#1a47a8' : '#b45309',
      letterSpacing: '0.06em',
      whiteSpace: 'nowrap',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#aaa' }} />
      {isAnd ? 'ET' : 'OU'}
      <Handle type="source" position={Position.Right} style={{ background: '#aaa' }} />
    </div>
  )
}

export const NODE_TYPES = { course: CourseNode, group: GroupNode }

export function applyLayout(nodeList, edgeList, completedSet, rootSigleSet, onRemoveChain) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', ranksep: 70, nodesep: 30, marginx: 20, marginy: 20 })

  nodeList.forEach(n => {
    const w = n.node_type === 'course' ? 180 : 64
    const h = n.node_type === 'course' ? 80 : 32
    g.setNode(n.id, { width: w, height: h })
  })
  edgeList.forEach(e => g.setEdge(e.source, e.target))

  dagre.layout(g)

  const rfNodes = nodeList.map(n => {
    const pos = g.node(n.id)
    const isRoot = rootSigleSet.has(n.id)
    return {
      id: n.id,
      type: n.node_type,
      position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 },
      data: {
        ...n.data,
        completed: n.node_type === 'course' && completedSet.has(n.id),
        isRoot,
        onRemoveChain: isRoot ? onRemoveChain : undefined,
      },
    }
  })

  const rfEdges = edgeList.map(e => {
    if (e.relation_type === 'equivalent') {
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: 'smoothstep',
        label: e.label,
        labelStyle: { fontSize: 10, fill: EQUIVALENT_COLOR, fontWeight: 600 },
        labelBgStyle: { fill: '#faf5ff', fillOpacity: 0.9 },
        style: { stroke: EQUIVALENT_COLOR, strokeWidth: 1.5, strokeDasharray: '4 3' },
        animated: false,
      }
    }
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'smoothstep',
      style: { stroke: '#bbb', strokeWidth: 1.5 },
      animated: false,
    }
  })

  return { rfNodes, rfEdges }
}
