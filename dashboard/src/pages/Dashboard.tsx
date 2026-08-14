import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'
import { Card, CardHeader, CardTitle, CardContent } from './ui/Card'
import { StatCard } from './ui/StatCard'
import { TimeRangeSelector } from './ui/TimeRangeSelector'
import { format } from 'date-fns'

interface BandwidthPoint {
  time: string
  bytes: number
}

interface TopTalker {
  src_ip: string
  value: number
}

interface ProtocolData {
  protocol: string
  bytes: number
}

export function Dashboard() {
  const [bandwidthData, setBandwidthData] = useState<BandwidthPoint[]>([])
  const [topTalkers, setTopTalkers] = useState<TopTalker[]>([])
  const [protocols, setProtocols] = useState<ProtocolData[]>([])
  const [timeRange, setTimeRange] = useState('-1h')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [timeRange])

  const fetchData = async () => {
    setLoading(true)
    try {
      const [bwRes, ttRes, protoRes] = await Promise.all([
        fetch(`/api/v1/bandwidth?start=${timeRange}&stop=now`).then(r => r.json()),
        fetch(`/api/v1/top-talkers?start=${timeRange}&stop=now&limit=10`).then(r => r.json()),
        fetch(`/api/v1/protocols?start=${timeRange}&stop=now`).then(r => r.json()),
      ])
      
      setBandwidthData(bwRes.series || [])
      setTopTalkers(ttRes.talkers || [])
      setProtocols(protoRes.distribution || [])
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  const totalBytes = bandwidthData.reduce((sum, d) => sum + (d.bytes || 0), 0)
  const totalPackets = 0 // Would need separate endpoint
  const activeAlerts = 0 // Would need alerts endpoint

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-text-muted">Real-time network flow overview</p>
        </div>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Bandwidth"
          value={formatBytes(totalBytes)}
          icon={<DownloadIcon />}
          trend="+12.5%"
          trendUp
        />
        <StatCard
          title="Active Flows"
          value={bandwidthData.length.toLocaleString()}
          icon={<ActivityIcon />}
          trend="+5.2%"
          trendUp
        />
        <StatCard
          title="Top Talkers"
          value={topTalkers.length.toString()}
          icon={<UsersIcon />}
          trend="Live"
        />
        <StatCard
          title="Active Alerts"
          value={activeAlerts.toString()}
          icon={<AlertIcon />}
          trend={activeAlerts > 0 ? 'Check alerts' : 'All clear'}
          trendUp={activeAlerts === 0}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Bandwidth Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Bandwidth Over Time</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={bandwidthData}>
                  <defs>
                    <linearGradient id="colorBandwidth" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--color-primary)" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="var(--color-primary)" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis 
                    dataKey="time" 
                    tickFormatter={(value) => format(new Date(value), 'HH:mm')}
                    stroke="var(--color-text-muted)"
                    fontSize={12}
                  />
                  <YAxis 
                    tickFormatter={(value) => formatBytes(value)}
                    stroke="var(--color-text-muted)"
                    fontSize={12}
                  />
                  <Tooltip 
                    formatter={(value: number) => [formatBytes(value), 'Bytes']}
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-md)',
                    }}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="bytes" 
                    stroke="var(--color-primary)" 
                    fillOpacity={1} 
                    fill="url(#colorBandwidth)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Protocol Distribution */}
        <Card>
          <CardHeader>
            <CardTitle>Protocol Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={protocols}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="bytes"
                    nameKey="protocol"
                    label={({ protocol, percent }) => `${protocol} ${(percent * 100).toFixed(1)}%`}
                  >
                    {protocols.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={`var(--chart-color-${index % 8})`} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => [formatBytes(value), 'Bytes']} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bottom Row - Top Talkers */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Top Talkers (by bytes)</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left text-text-muted text-sm">
                  <th className="pb-3 pr-4">Rank</th>
                  <th className="pb-3 pr-4">Source IP</th>
                  <th className="pb-3 pr-4">Bytes</th>
                  <th className="pb-3 pr-4">% of Total</th>
                </tr>
              </thead>
              <tbody>
                {topTalkers.slice(0, 10).map((talker, index) => (
                  <tr key={talker.src_ip} className="border-b border-border/50 hover:bg-surface-hover transition-colors">
                    <td className="py-3 pr-4 font-medium text-text-muted">#{index + 1}</td>
                    <td className="py-3 pr-4 font-mono">{talker.src_ip}</td>
                    <td className="py-3 pr-4">{formatBytes(talker.value)}</td>
                    <td className="py-3 pr-4">
                      <div className="w-32 h-2 bg-border rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-primary" 
                          style={{ width: `${((talker.value / (totalBytes || 1)) * 100).toFixed(1)}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// Helper Icons
function DownloadIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
}

function ActivityIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
}

function UsersIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
}

function AlertIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// Missing PieChart components
import { PieChart, Pie, Cell, Tooltip } from 'recharts'