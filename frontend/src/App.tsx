import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Layout from './components/Layout'
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
import ToastCenter from './components/ToastCenter'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5 * 60_000,      // 5 minutes — prevents re-fetching on route change
      gcTime: 10 * 60_000,         // 10 minutes cache retention
      refetchOnWindowFocus: false, // prevents refetch when switching browser tabs
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastCenter />
        <Routes>
          <Route path="/" element={<Layout />}>
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
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
