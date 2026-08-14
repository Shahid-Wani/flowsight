import { useState, useEffect, useCallback } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Table } from '../ui/Table'
import { TimeRangeSelector } from '../ui/TimeRangeSelector'
import { Badge } from '../ui/Badge'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { useWebSocket } from '../hooks/useWebSocket'
import { formatBytes, formatNumber } from '../utils/format'

interface ProtocolData {
  protocol: string
  bytes: number
  packets?: number
  flows?: number
}

interface WSMessage {
  type: string
  data: any
}

export function ProtocolDistribution() {
  const [protocols, setProtocols] = useState<ProtocolData[]>([])
  const [timeRange, setTimeRange] = useState('-1h')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const { isConnected, lastMessage } = useWebSocket('/api/v1/ws/live')

  // Handle WebSocket messages for real-time protocol updates
  useEffect(() => {
    if (lastMessage) {
      try {
        const message: WSMessage = JSON.parse(lastMessage.data)
        if (message.type === 'protocols_update' && Array.isArray(message.data)) {
          setProtocols(message.data)
        }
      } catch (e) {
        console.error('Failed to parse WS message:', e)
      }
    }
  }, [lastMessage])

  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/v1/protocols?start=${timeRange}&stop=now`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setProtocols(data.distribution || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch protocol distribution')
    } finally {
      setLoading(false)
    }
  }, [timeRange])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  const totalBytes = protocols.reduce((sum, d) => sum + (d.bytes || 0), 0)
  const totalPackets = protocols.reduce((sum, d) => sum + (d.packets || 0), 0)
  const totalFlows = protocols.reduce((sum, d) => sum + (d.flows || 0), 0)

  const COLORS = [
    '#3b82f6', '#10b981', '#f59e0b', '#ef4444', 
    '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'
  ]

  const PROTOCOL_ICONS: Record<string, string> = {
    'TCP': '🔵', 'UDP': '🟢', 'ICMP': '🟡', 'ICMPv6': '🟠',
    'IGMP': '🟣', 'GRE': '🔴', 'ESP': '⚫', 'AH': '⚪',
    'SCTP': '🟤', 'IPv6': '🔷', 'Other': '⚪'
  }

  const columns = [
    { 
      key: 'protocol', 
      header: 'Protocol', 
      render: (row: ProtocolData) => (
        <span className="flex items-center gap-2 font-medium">
          <span>{PROTOCOL_ICONS[row.protocol] || '📦'}</span>
          <span>{row.protocol}</span>
        </span>
      )
    },
    { 
      key: 'bytes', 
      header: 'Bytes', 
      sortable: true,
      render: (row: ProtocolData) => (
        <span className="font-mono">{formatBytes(row.bytes)}</span>
      )
    },
    { 
      key: 'packets', 
      header: 'Packets', 
      sortable: true,
      render: (row: ProtocolData) => 
        row.packets ? <span className="font-mono">{formatNumber(row.packets)}</span> : <span className="text-text-muted">—</span>
    },
    { 
      key: 'flows', 
      header: 'Flows', 
      sortable: true,
      render: (row: ProtocolData) => 
        row.flows ? <span className="font-mono">{formatNumber(row.flows)}</span> : <span className="text-text-muted">—</span>
    },
    { 
      key: 'percentage', 
      header: '% of Total', 
      render: (row: ProtocolData) => {
        const pct = totalBytes > 0 ? ((row.bytes / totalBytes) * 100).toFixed(1) : '0.0'
        return (
          <div className="w-32">
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-border rounded-full overflow-hidden">
                <div 
                  className="h-full bg-primary transition-all duration-500" 
                  style={{ width: `${Math.min(parseFloat(pct), 100)}%` }}
                />
              </div>
              <span className="text-sm font-mono w-12 text-right">{pct}%</span>
            </div>
          </div>
        )
      }
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Protocol Distribution</h1>
          <p className="text-text-muted">Traffic breakdown by network protocol</p>
        </div>
        <div className="flex items-center gap-4">
          <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pie Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Protocol Distribution (by Bytes)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={protocols}
                    cx="50%"
                    cy="50%"
                    innerRadius={80}
                    outerRadius={140}
                    paddingAngle={3}
                    dataKey="bytes"
                    nameKey="protocol"
                    label={({ protocol, percent }) => `${protocol} ${(percent * 100).toFixed(1)}%`}
                    labelLine={false}
                  >
                    {protocols.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    formatter={(value: number, name: string) => [formatBytes(value), name]}
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-md)',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Stats Summary */}
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
              <StatCard
                title="Total Bytes"
                value={formatBytes(totalBytes)}
                icon={<DownloadIcon />}
              />
              <StatCard
                title="Total Packets"
                value={formatNumber(totalPackets)}
                icon={<ActivityIcon />}
              />
              <StatCard
                title="Total Flows"
                value={formatNumber(totalFlows)}
                icon={<UsersIcon />}
              />
            </div>
            
            <Table 
              columns={[
                { 
                  key: 'protocol', 
                  header: 'Protocol', 
                  render: (row: ProtocolData) => (
                    <span className="flex items-center gap-2 font-medium">
                      <span>{PROTOCOL_ICONS[row.protocol] || '📦'}</span>
                      <span>{row.protocol}</span>
                    </span>
                  )
                },
                { 
                  key: 'bytes', 
                  header: 'Bytes', 
                  render: (row: ProtocolData) => <span className="font-mono">{formatBytes(row.bytes)}</span> 
                },
                { 
                  key: 'packets', 
                  header: 'Packets', 
                  render: (row: ProtocolData) => 
                    row.packets ? <span className="font-mono">{formatNumber(row.packets)}</span> : <span className="text-text-muted">—</span> 
                },
                { 
                  key: 'flows', 
                  header: 'Flows', 
                  render: (row: ProtocolData) => 
                    row.flows ? <span className="font-mono">{formatNumber(row.flows)}</span> : <span className="text-text-muted">—</span> 
                },
                { 
                  key: 'percentage', 
                  header: '% of Total', 
                  render: (row: ProtocolData) => {
                    const pct = totalBytes > 0 ? ((row.bytes / totalBytes) * 100).toFixed(1) : '0.0'
                    return (
                      <div className="w-32">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-border rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-primary transition-all duration-500" 
                              style={{ width: `${Math.min(parseFloat(pct), 100)}%` }}
                            />
                          </div>
                          <span className="text-sm font-mono w-12 text-right">{pct}%</span>
                        </div>
                      </div>
                    )
                  }
              ]} 
              data={protocols} 
              striped
              hoverable
            />
          </CardContent>
        </Card>
      </div>

      {/* Protocol Details */}
      <Card>
        <CardHeader>
          <CardTitle>Protocol Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {protocols.map((proto) => (
              <div key={proto.protocol} className="p-4 bg-background rounded-lg border border-border hover:border-primary/50 transition-colors">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-2xl">{PROTOCOL_ICONS[proto.protocol] || '📦'}</span>
                  <span className="font-semibold text-lg">{proto.protocol}</span>
                </div>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-muted">Bytes</span>
                    <span className="font-mono">{formatBytes(proto.bytes)}</span>
                  </div>
                  {proto.packets && (
                    <div className="flex justify-between">
                      <span className="text-text-muted">Packets</span>
                      <span className="font-mono">{formatNumber(proto.packets)}</span>
                    </div>
                  )}
                  {proto.flows && (
                    <div className="flex justify-between">
                      <span className="text-text-muted">Flows</span>
                      <span className="font-mono">{formatNumber(proto.flows)}</span>
                    </div>
                  )}
                  <div className="flex justify-between pt-2 border-t border-border">
                    <span className="text-text-muted">Share</span>
                    <span className="font-semibold text-primary">
                      {totalBytes > 0 ? ((proto.bytes / totalBytes) * 100).toFixed(1) : '0.0'}%
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
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

function DownloadIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
}

function ActivityIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
}

function UsersIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
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

function DownloadIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
}

function ActivityIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
}

interface WSMessage {
  type: string
  data: any
}