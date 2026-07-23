import { useEffect, useState } from 'react'
import ExplorationPage from './ExplorationPage'
import AdminPanel from './AdminPanel'

const DEMO_COMPLETED = [
  'IFT1005',
  'IFT1015',
  'IFT1025',
  'IFT1065',
  'IFT1575',
  'IFT1215',
  'IFT1227',
  'MAT1400',
  'MAT1600',
  'MAT1978',
].map(sigle => ({ sigle, universite: 'UdeM' }))

export default function App() {
  const [showAdmin, setShowAdmin] = useState(false)

  const [completed, setCompleted] = useState(() => {
    const raw = localStorage.getItem('completed')
    if (raw == null) return DEMO_COMPLETED
    try { return JSON.parse(raw) } catch { return [] }
  })
  useEffect(() => {
    localStorage.setItem('completed', JSON.stringify(completed))
  }, [completed])

  const [homeUniversite, setHomeUniversite] = useState(() =>
    localStorage.getItem('homeUniversite') || 'UdeM'
  )
  useEffect(() => {
    homeUniversite
      ? localStorage.setItem('homeUniversite', homeUniversite)
      : localStorage.removeItem('homeUniversite')
  }, [homeUniversite])

  function markCompleted(course) {
    setCompleted(prev => prev.some(c => c.sigle === course.sigle) ? prev : [...prev, course])
  }

  function removeCourse(sigle) {
    setCompleted(prev => prev.filter(c => c.sigle !== sigle))
  }

  return (
    <div className="app-shell">
      <nav className="app-tabbar">
        <span className="app-brand">Astra</span>
        <button
          className={`tab-btn-admin${showAdmin ? ' active' : ''}`}
          onClick={() => setShowAdmin(v => !v)}
        >
          Admin
        </button>
      </nav>

      <div className="app-content">
        {showAdmin ? (
          <AdminPanel onBack={() => setShowAdmin(false)} />
        ) : (
          <ExplorationPage
            completed={completed}
            onAddCompleted={markCompleted}
            onRemoveCompleted={removeCourse}
            homeUniversite={homeUniversite}
            onSetHome={setHomeUniversite}
          />
        )}
      </div>
    </div>
  )
}
