import { useState, useEffect, useCallback } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Table } from '../ui/Table'
import { TimeRangeSelector } from '../ui/TimeRangeSelector'
import { Badge } from '../ui/Badge'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import { Button } from '../ui/Button'
import { useWebSocket } from '../hooks/useWebSocket'
import { formatBytes, formatNumber } from '../utils/format'

interface Alert {
  id: string
  rule_name: string
  severity: 'info' | 'warning' | 'critical'
  message: string
  flow_data: Record<string, any>
  timestamp: string
  acknowledged: boolean
  acknowledged_by?: string
  acknowledged_at?: string
}

interface AlertSummary {
  total: number
  critical: number
  warning: number
  info: number
}

interface WSMessage {
  type: string
  data: any
}

export function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [summary, setSummary] = useState<AlertSummary>({ total: 0, critical: 0, warning: 0, info: 0 })
  const [timeRange, setTimeRange] = useState('-1h')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null)
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'timestamp', direction: 'desc' })

  const { isConnected, lastMessage } = useWebSocket('/api/v1/ws/live')

  // Handle WebSocket messages for real-time alerts
  useEffect(() => {
    if (lastMessage) {
      try {
        const message: WSMessage = JSON.parse(lastMessage.data)
        if (message.type === 'alert' && message.data) {
          setAlerts(prev => [message.data, ...prev.slice(0, 99)]) // Keep last 100
          updateSummary()
        }
      } catch (e) {
        console.error('Failed to parse WS message:', e)
      }
    }
  }, [lastMessage])

  const updateSummary = () => {
    const newSummary = alerts.reduce((acc, alert) => {
      acc.total++
      acc[alert.severity]++
      return acc
    }, { total: 0, critical: 0, warning: 0, info: 0 })
    setSummary(newSummary)
  }

  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/v1/alerts?start=${timeRange}&stop=now&limit=100`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setAlerts(data.alerts || [])
      updateSummary()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch alerts')
    } finally {
      setLoading(false)
    }
  }, [timeRange])

  useEffect(() => {
    fetchData()
    updateSummary()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  // Sorting
  const handleSort = (key: string) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
  }

  const sortedAlerts = [...alerts].sort((a, b) => {
    const aVal = (a as any)[sortConfig.key]
    const bVal = (b as any)[sortConfig.key]
    if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1
    if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1
    return 0
  })

  const acknowledgeAlert = async (alert: Alert) => {
    try {
      const res = await fetch(`/api/v1/alerts/${alert.id}/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      if (res.ok) {
        setAlerts(prev => prev.map(a => a.id === alert.id ? { ...a, acknowledged: true, acknowledged_at: new Date().toISOString() } : a))
        updateSummary()
      }
    } catch (err) {
      console.error('Failed to acknowledge alert:', err)
    }
  }

  const severityColors = {
    critical: { badge: 'danger', icon: '🔴', bg: 'bg-red-500/10 border-red-500/20' },
    warning: { badge: 'warning', icon: '🟡', bg: 'bg-yellow-500/10 border-yellow-500/20' },
    info: { badge: 'info', icon: '🔵', bg: 'bg-blue-500/10 border-blue-500/20' },
  }

  const columns = [
    { 
      key: 'severity', 
      header: 'Severity', 
      sortable: true,
      render: (row: Alert) => (
        <Badge variant={severityColors[row.severity].badge}>
          {severityColors[row.severity].icon} {row.severity.toUpperCase()}
        </Badge>
      )
    },
    { 
      key: 'rule_name', 
      header: 'Rule', 
      sortable: true,
      render: (row: Alert) => (
        <span className="font-medium">{row.rule_name}</span>
      )
    },
    { 
      key: 'message', 
      header: 'Message', 
      render: (row: Alert) => (
        <span className="max-w-md truncate block" title={row.message}>{row.message}</span>
      )
    },
    { 
      key: 'src_ip', 
      header: 'Source IP', 
      sortable: true,
      render: (row: Alert) => (
        <span className="font-mono text-sm">{row.flow_data?.src_ip || '—'}</span>
      )
    },
    { 
      key: 'dst_ip', 
      header: 'Dest IP', 
      sortable: true,
      render: (row: Alert) => (
        <span className="font-mono text-sm">{row.flow_data?.dst_ip || '—'}</span>
      )
    },
    { 
      key: 'bytes', 
      header: 'Bytes', 
      sortable: true,
      render: (row: Alert) => (
        <span className="font-mono">{row.flow_data?.bytes ? formatBytes(row.flow_data.bytes) : '—'}</span>
      )
    },
    { 
      key: 'timestamp', 
      header: 'Time', 
      sortable: true,
      render: (row: Alert) => (
        <span className="font-mono text-sm">{new Date(row.timestamp).toLocaleString()}</span>
      )
    },
    { 
      key: 'status', 
      header: 'Status', 
      render: (row: Alert) => (
        <Badge variant={row.acknowledged ? 'success' : 'warning'}>
          {row.acknowledged ? '✓ Acknowledged' : '⏳ Pending'}
        </Badge>
      )
    },
    { 
      key: 'actions', 
      header: 'Actions', 
      render: (row: Alert) => (
        <div className="flex items-center gap-2">
          {!row.acknowledged && (
            <button
              onClick={() => acknowledgeAlert(row)}
              className="text-sm text-primary hover:underline"
            >
              Acknowledge
            </button>
          )}
          <button
            onClick={() => setSelectedAlert(row)}
            className="text-sm text-primary hover:underline"
          >
            Details
          </button>
        </div>
      )
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Alerts</h1>
          <p className="text-text-muted">Threshold-based anomaly alerts</p>
        </div>
        <div className="flex items-center gap-4">
          <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
            isConnected ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-400'}`} />
            <span>{isConnected ? 'Live' : 'Historical'}</span>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <StatCard
          title="Total Alerts"
          value={summary.total.toString()}
          icon={<AlertIcon />}
          trend={summary.total > 0 ? 'Active' : 'Clear'}
          trendUp={summary.total === 0}
        />
        <StatCard
          title="Critical"
          value={summary.critical.toString()}
          icon={<AlertIcon />}
          trend="High"
          trendUp={summary.critical === 0}
        />
        <StatCard
          title="Warning"
          value={summary.warning.toString()}
          icon={<WarningIcon />}
          trend="Medium"
          trendUp={summary.warning === 0}
        />
        <StatCard
          title="Info"
          value={summary.info.toString()}
          icon={<InfoIcon />}
          trend="Low"
          trendUp={summary.info === 0}
        />
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={fetchData} className="text-sm underline">Retry</button>
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Alerts ({alerts.length})</CardTitle>
          <div className="flex items-center gap-4 text-sm text-text-muted">
            <span>Critical: {summary.critical}</span>
            <span>•</span>
            <span>Warning: {summary.warning}</span>
            <span>•</span>
            <span>Info: {summary.info}</span>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-12 text-text-muted">
              <div className="animate-spin inline-block w-8 h-8 border-4 border-primary border-t-transparent rounded-full mb-2 mx-auto" />
              <p>Loading alerts...</p>
            </div>
          ) : alerts.length === 0 ? (
            <div className="text-center py-12 text-text-muted">
              <AlertCircleIcon className="w-12 h-12 mx-auto mb-2 text-text-dim" />
              <h3 className="text-lg font-medium mb-1">No alerts</h3>
              <p className="text-text-muted">All clear! No threshold violations detected.</p>
            </div>
          ) : (
            <Table 
              columns={columns} 
              data={sortedAlerts} 
              striped
              hoverable
              onRowClick={(row) => setSelectedAlert(row)}
            />
          )}
        </CardContent>
      </Card>

      {selectedAlert && (
        <AlertDetailModal 
          alert={selectedAlert} 
          onClose={() => setSelectedAlert(null)} 
        />
      )}
    </div>
  )
}

function AlertDetailModal({ alert, onClose }: { alert: Alert; onClose: () => void }) {
  const severityColors = {
    critical: { badge: 'danger', bg: 'bg-red-500/10 border-red-500/20 text-red-400' },
    warning: { badge: 'warning', bg: 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400' },
    info: { badge: 'info', bg: 'bg-blue-500/10 border-blue-500/20 text-blue-400' },
  }
  
  const colors = severityColors[alert.severity]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-surface border border-border rounded-lg shadow-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto">
        <div className="p-6 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Badge variant={alert.severity} className="text-sm">
              {alert.severity.toUpperCase()}
            </Badge>
            <h3 className="text-lg font-semibold">{alert.rule_name}</h3>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text p-1">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="p-6 space-y-4">
          <div className={`p-4 rounded-lg border ${colors.bg.replace('bg-', '').replace('border-', '').split(' ')[0]}`}>
            <p className="font-medium">{alert.message}</p>
          </div>
          
          <dl className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <dt className="text-text-muted">Timestamp</dt>
                <dd className="font-mono">{new Date(alert.timestamp).toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-text-muted">Status</dt>
                <dd className="flex items-center gap-2">
                  <Badge variant={alert.acknowledged ? 'success' : 'warning'}>
                    {alert.acknowledged ? 'Acknowledged' : 'Pending'}
                  </Badge>
                </dd>
              </div>
            </div>
            
            {alert.acknowledged && alert.acknowledged_at && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <dt className="text-text-muted">Acknowledged At</dt>
                  <dd className="font-mono">{new Date(alert.acknowledged_at).toLocaleString()}</dd>
                </div>
                {alert.acknowledged_by && (
                  <div>
                    <dt className="text-text-muted">Acknowledged By</dt>
                    <dd>{alert.acknowledged_by}</dd>
                  </div>
                )}
              </div>
            )}
            
            <div>
              <dt className="text-text-muted">Flow Details</dt>
              <dd className="mt-2 p-3 bg-background rounded-lg font-mono text-sm max-h-40 overflow-y-auto">
                <pre>{JSON.stringify(alert.flow_data, null, 2)}</pre>
              </dd>
            </div>
          </dl>
        </div>
        <div className="p-6 border-t border-border flex justify-end gap-2">
          {!alert.acknowledged && (
            <button
              onClick={() => {
                // TODO: Implement acknowledge API call
                alert.acknowledged = true
                alert.acknowledged_at = new Date().toISOString()
              }}
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-hover transition-colors"
            >
              Acknowledge
            </button>
          )}
          <button onClick={onClose} className="px-4 py-2 bg-surface border border-border rounded-lg hover:bg-surface-hover transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

function StatCard({ title, value, icon, trend, trendUp }: { title: string; value: string; icon: React.ReactNode; trend?: string; trendUp?: boolean }) {
  return (
    <div className="p-4 bg-background rounded-lg border border-border">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-text-muted">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {trend && (
            <p className={`mt-1 text-sm font-medium ${trendUp ? 'text-green-400' : 'text-red-400'}`}>
              {trend}
            </p>
          )}
        </div>
        <div className="p-3 bg-primary/10 rounded-lg text-primary">{icon}</div>
      </div>
    </div>
  )
}

function AlertIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
}

function WarningIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
}

function InfoIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
}

function AlertCircleIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
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

interface WSMessage {
  type: string
  data: any
}