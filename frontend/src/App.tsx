import { BrowserRouter, Route, Routes } from 'react-router-dom'
import HealthCheckPage from './pages/HealthCheckPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HealthCheckPage />} />
      </Routes>
    </BrowserRouter>
  )
}
