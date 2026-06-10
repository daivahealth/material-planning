import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './contexts/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Hospitals from './pages/Hospitals'
import Stores from './pages/Stores'
import Items from './pages/Items'
import Suppliers from './pages/Suppliers'
import Settings from './pages/Settings'
import Imports from './pages/Imports'
import IndentPlanning from './pages/IndentPlanning'
import Surges from './pages/Surges'
import Classification from './pages/Classification'
import Scheduler from './pages/Scheduler'
import ConsumptionAnalysis from './pages/ConsumptionAnalysis'
import DataMining from './pages/DataMining'
import Users from './pages/Users'
import ToastCenter from './components/ToastCenter'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5 * 60_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <ToastCenter />
          <Routes>
            {/* Public route */}
            <Route path="/login" element={<Login />} />

            {/* All other routes require authentication */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="hospitals" element={<Hospitals />} />
              <Route path="stores" element={<Stores />} />
              <Route path="items" element={<Items />} />
              <Route path="suppliers" element={<Suppliers />} />
              <Route path="settings" element={<Settings />} />
              <Route path="imports" element={<Imports />} />
              <Route path="indents" element={<IndentPlanning />} />
              <Route path="surges" element={<Surges />} />
              <Route path="classification" element={<Classification />} />
              <Route path="scheduler" element={<Scheduler />} />
              <Route path="consumption" element={<ConsumptionAnalysis />} />
              <Route path="data-mining" element={<DataMining />} />
              {/* Users page — master only */}
              <Route
                path="users"
                element={
                  <ProtectedRoute masterOnly>
                    <Users />
                  </ProtectedRoute>
                }
              />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
