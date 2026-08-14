import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { TimeRangeSelector } from '../ui/TimeRangeSelector'
import { Table } from '../ui/Table'
import { Badge } from '../ui/Badge'
import { formatBytes, formatNumber } from '../utils/format'

interface GeoLocation {
  country_code: string
  country_name: string
  latitude: number
  longitude: number
  bytes_sent: number
  bytes_received: number
  flows: number
  unique_ips: number
}

export function GeoMap() {
  const [geoData, setGeoData] = useState<GeoLocation[]>([])
  const [timeRange, setTimeRange] = useState('-1h')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'map' | 'table'>('table')
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'bytes_sent', direction: 'desc' })

  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/v1/geo-map?start=${timeRange}&stop=now`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setGeoData(data.locations || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch geo data')
    } finally {
      setLoading(false)
    }
  }, [timeRange])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60000) // Refresh every minute
    return () => clearInterval(interval)
  }, [fetchData])

  // Sorting
  const handleSort = (key: string) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
  }

  const sortedData = [...geoData].sort((a, b) => {
    const aVal = (a as any)[sortConfig.key]
    const bVal = (b as any)[sortConfig.key]
    if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1
    if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1
    return 0
  })

  const totalSent = geoData.reduce((sum, d) => sum + (d.bytes_sent || 0), 0)
  const totalReceived = geoData.reduce((sum, d) => sum + (d.bytes_received || 0), 0)
  const totalFlows = geoData.reduce((sum, d) => sum + (d.flows || 0), 0)

  const columns = [
    { 
      key: 'country', 
      header: 'Country', 
      render: (row: GeoLocation) => (
        <span className="flex items-center gap-2 font-medium">
          <span className="text-lg">{getCountryFlag(row.country_code)}</span>
          <span>{row.country_name}</span>
        </span>
      )
    },
    { 
      key: 'bytes_sent', 
      header: 'Bytes Sent', 
      sortable: true,
      render: (row: GeoLocation) => <span className="font-mono">{formatBytes(row.bytes_sent)}</span>
    },
    { 
      key: 'bytes_received', 
      header: 'Bytes Received', 
      sortable: true,
      render: (row: GeoLocation) => <span className="font-mono">{formatBytes(row.bytes_received)}</span>
    },
    { 
      key: 'total_bytes', 
      header: 'Total Bytes', 
      sortable: true,
      render: (row: GeoLocation) => <span className="font-mono font-semibold">{formatBytes(row.bytes_sent + row.bytes_received)}</span>
    },
    { 
      key: 'flows', 
      header: 'Flows', 
      sortable: true,
      render: (row: GeoLocation) => <span className="font-mono">{formatNumber(row.flows)}</span>
    },
    { 
      key: 'unique_ips', 
      header: 'Unique IPs', 
      sortable: true,
      render: (row: GeoLocation) => <span className="font-mono">{formatNumber(row.unique_ips)}</span>
    },
  ]

  const sortedCountries = [...geoData].sort((a, b) => {
    const aVal = (a as any)[sortConfig.key]
    const bVal = (b as any)[sortConfig.key]
    if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1
    if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1
    return 0
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Geo Map</h1>
          <p className="text-text-muted">Geographic distribution of network traffic</p>
        </div>
        <div className="flex items-center gap-4">
          <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
          <div className="flex gap-2">
            <button
              onClick={() => setViewMode('table')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                viewMode === 'table' 
                  ? 'bg-primary text-white' 
                  : 'bg-surface border border-border hover:bg-surface-hover'
              }`}
            >
              Table
            </button>
            <button
              onClick={() => setViewMode('map')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                viewMode === 'map' 
                  ? 'bg-primary text-white' 
                  : 'bg-surface border border-border hover:bg-surface-hover'
              }`}
            >
              Map
            </button>
          </div>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Total Sent"
          value={formatBytes(geoData.reduce((sum, d) => sum + (d.bytes_sent || 0), 0))}
          icon={<UploadIcon />}
        />
        <StatCard
          title="Total Received"
          value={formatBytes(geoData.reduce((sum, d) => sum + (d.bytes_received || 0), 0))}
          icon={<DownloadIcon />}
        />
        <StatCard
          title="Total Flows"
          value={formatNumber(geoData.reduce((sum, d) => sum + (d.flows || 0), 0))}
          icon={<ActivityIcon />}
        />
      </div>

      {viewMode === 'map' ? (
        <Card className="h-[600px]">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>World Map - Traffic Volume</CardTitle>
              <Badge variant="warning">Coming Soon</Badge>
            </div>
          </CardHeader>
          <CardContent className="h-[500px] flex items-center justify-center">
            <div className="text-center text-text-muted max-w-md">
              <svg className="w-24 h-24 mx-auto mb-4 text-text-dim" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.303A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15l3-3m0 0l-3-3m3 3H9" />
              </svg>
              <h3 className="text-xl font-semibold mb-2">Interactive World Map</h3>
              <p className="text-text-muted mb-4">
                Geographic visualization of traffic origins and destinations with choropleth mapping.
              </p>
              <div className="max-w-md mx-auto text-left text-sm space-y-2">
                <p className="font-medium mb-2">Planned Features:</p>
                <ul className="space-y-1 text-text-muted">
                  <li>• Choropleth map (traffic volume by country)</li>
                  <li>• Source/destination connection lines</li>
                  <li>• Real-time attack origin tracking</li>
                  <li>• Drill-down to ASN/ISP level</li>
                  <li>• Heatmap of suspicious activity</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Countries by Traffic Volume</CardTitle>
              <div className="flex items-center gap-2 text-sm text-text-muted">
                <span>{geoData.length} countries</span>
                <span>•</span>
                <span>Updated: {new Date().toLocaleTimeString()}</span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {geoData.length === 0 ? (
              <div className="text-center py-12 text-text-muted">
                <p>No geographic data available for this time range</p>
              </div>
            ) : (
              <Table 
                columns={[
                  { 
                    key: 'country', 
                    header: 'Country', 
                    render: (row: GeoLocation) => (
                      <span className="flex items-center gap-2 font-medium">
                        <span className="text-lg">{getCountryFlag(row.country_code)}</span>
                        <span>{row.country_name}</span>
                      </span>
                    )
                  },
                  { 
                    key: 'bytes_sent', 
                    header: 'Bytes Sent', 
                    sortable: true,
                    render: (row: GeoLocation) => <span className="font-mono">{formatBytes(row.bytes_sent)}</span>
                  },
                  { 
                    key: 'bytes_received', 
                    header: 'Bytes Received', 
                    sortable: true,
                    render: (row: GeoLocation) => <span className="font-mono">{formatBytes(row.bytes_received)}</span>
                  },
                  { 
                    key: 'total', 
                    header: 'Total', 
                    sortable: true,
                    render: (row: GeoLocation) => <span className="font-mono font-semibold">{formatBytes(row.bytes_sent + row.bytes_received)}</span>
                  },
                  { 
                    key: 'flows', 
                    header: 'Flows', 
                    sortable: true,
                    render: (row: GeoLocation) => <span className="font-mono">{formatNumber(row.flows)}</span>
                  },
                  { 
                    key: 'unique_ips', 
                    header: 'Unique IPs', 
                    sortable: true,
                    render: (row: GeoLocation) => <span className="font-mono">{formatNumber(row.unique_ips)}</span>
                  },
                ]} 
                data={geoData
                  .sort((a, b) => {
                    const aVal = (a as any)[sortConfig.key]
                    const bVal = (b as any)[sortConfig.key]
                    if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1
                    if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1
                    return 0
                  })}
                striped
                hoverable
              />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function StatCard({ title, value, icon }: { title: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="p-4 bg-background rounded-lg border border-border">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-text-muted">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
        </div>
        <div className="p-2 bg-primary/10 rounded-lg text-primary">{icon}</div>
      </div>
    </div>
  )
}

function UploadIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
}

function DownloadIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
}

function ActivityIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
}

function getCountryFlag(code: string): string {
  if (!code || code.length !== 2) return '🏳️'
  const offset = 127397
  return String.fromCodePoint(...code.toUpperCase().split('').map(c => c.charCodeAt(0) + offset))
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

function formatNumber(num: number): string {
  if (num === 0) return '0'
  return new Intl.NumberFormat().format(num)
}