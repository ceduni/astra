import { useEffect, useState } from 'react'
import AccessiblePage from './AccessiblePage'
import EquivalencesPage from './EquivalencesPage'
import VisualiseurPage from './VisualiseurPage'
import AdminPanel from './AdminPanel'

const TABS = [
  { id: 'accessible',   label: 'Cours accessibles' },
  { id: 'equivalences', label: 'Équivalences' },
  { id: 'visualiseur',  label: 'Visualiseur' },
]

export default function App() {
  const [tab, setTab] = useState('accessible')

  // ── Shared persistent state ──────────────────────────────────────────────────

  const [completed, setCompleted] = useState(() => {
    try { return JSON.parse(localStorage.getItem('completed') || '[]') } catch { return [] }
  })
  useEffect(() => {
    localStorage.setItem('completed', JSON.stringify(completed))
  }, [completed])

  const [homeUniversite, setHomeUniversite] = useState(() =>
    localStorage.getItem('homeUniversite') || null
  )
  useEffect(() => {
    homeUniversite
      ? localStorage.setItem('homeUniversite', homeUniversite)
      : localStorage.removeItem('homeUniversite')
  }, [homeUniversite])

  // ── Visualiseur-specific state (kept here so it survives tab switches) ────────

  const [chainsToLoad, setChainsToLoad] = useState([])
  const [selectedCourse, setSelectedCourse] = useState(null)
  const [resetKey, setResetKey] = useState(0)

  // ── Course actions ────────────────────────────────────────────────────────────

  function markCompleted(course) {
    setCompleted(prev => prev.some(c => c.sigle === course.sigle) ? prev : [...prev, course])
  }

  function removeCourse(sigle) {
    setCompleted(prev => prev.filter(c => c.sigle !== sigle))
  }

  function addChain(sigle) {
    setChainsToLoad(prev => prev.includes(sigle) ? prev : [...prev, sigle])
  }

  function removeChain(sigle) {
    setChainsToLoad(prev => prev.filter(s => s !== sigle))
    setSelectedCourse(prev => prev?.sigle === sigle ? null : prev)
  }

  function resetGraph() {
    setSelectedCourse(null)
    setChainsToLoad([])
    setResetKey(k => k + 1)
  }

  return (
    <div className="app-shell">
      {/* ── Tab bar ── */}
      <nav className="app-tabbar">
        <span className="app-brand">Astra</span>
        <div className="app-tabs">
          {TABS.map(t => (
            <button
              key={t.id}
              className={`tab-btn${tab === t.id ? ' active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <button
          className={`tab-btn-admin${tab === 'admin' ? ' active' : ''}`}
          onClick={() => setTab('admin')}
        >
          Admin
        </button>
      </nav>

      {/* ── Content ── */}
      <div className="app-content">
        {tab === 'accessible' && (
          <AccessiblePage
            completed={completed}
            onAddCompleted={markCompleted}
            onRemoveCompleted={removeCourse}
            homeUniversite={homeUniversite}
            onSetHome={setHomeUniversite}
          />
        )}

        {tab === 'equivalences' && <EquivalencesPage />}

        {tab === 'visualiseur' && (
          <VisualiseurPage
            completed={completed}
            onAddCompleted={markCompleted}
            onRemoveCompleted={removeCourse}
            chainsToLoad={chainsToLoad}
            onAddChain={addChain}
            onRemoveChain={removeChain}
            resetKey={resetKey}
            onResetGraph={resetGraph}
            selectedCourse={selectedCourse}
            onSelectCourse={setSelectedCourse}
          />
        )}

        {tab === 'admin' && (
          <AdminPanel onBack={() => setTab('accessible')} />
        )}
      </div>
    </div>
  )
}
