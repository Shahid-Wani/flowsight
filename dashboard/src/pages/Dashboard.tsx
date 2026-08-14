import { useState, useEffect, useRef } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, PieChart, Pie, Cell, Tooltip as RechartsTooltip } from 'recharts'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { StatCard } from '../ui/StatCard'
import { TimeRangeSelector } from '../ui/TimeRangeSelector'
import { useWebSocket } from '../hooks/useWebSocket'
import { formatBytes, formatNumber } from '../utils/format'

interface BandwidthPoint {
  time: string
  bytes: number
  packets?: number
}

interface TopTalker {
  src_ip: string
  value: number
}

interface ProtocolData {
  protocol: string
  bytes: number
}

interface WSMessage {
  type: string
  data: any
}

export function Dashboard() {
  const [bandwidthData, setBandwidthData] = useState<BandwidthPoint[]>([])
  const [topTalkers, setTopTalkers] = useState<TopTalker[]>([])
  const [protocols, setProtocols] = useState<ProtocolData[]>([])
  const [timeRange, setTimeRange] = useState('-1h')
  const [loading, setLoading] = useState(true)
  const [wsConnected, setWsConnected] = useState(false)
  
  // For real-time updates
  const bandwidthHistoryRef = useRef<Map<string, number>>(new Map())
  const maxHistoryPoints = 120 // 2 minutes at 1s interval

  const { isConnected, lastMessage } = useWebSocket('/api/v1/ws/live')

  // Handle WebSocket messages
  useEffect(() => {
    setWsConnected(isConnected)
    
    if (lastMessage) {
      try {
        const message: WSMessage = JSON.parse(lastMessage.data)
        handleWSMessage(message)
      } catch (e) {
        console.error('Failed to parse WS message:', e)
      }
    }
  }, [isConnected, lastMessage])

  const handleWSMessage = (message: WSMessage) => {
    switch (message.type) {
      case 'bandwidth_update':
        if (message.data && message.data.time && message.data.bytes !== undefined) {
          setBandwidthData(prev => {
            const newData = [...prev, { 
              time: message.data.time, 
              bytes: message.data.bytes,
              packets: message.data.packets 
            }]
            // Keep only last maxHistoryPoints
            return newData.slice(-maxHistoryPoints)
          })
        }
        break
      case 'top_talkers_update':
        if (message.data && Array.isArray(message.data)) {
          setTopTalkers(message.data)
        }
        break
    }
  }

  // Initial data fetch and periodic refresh
  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
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
  })

  const totalBytes = bandwidthData.reduce((sum, d) => sum + (d.bytes || 0), 0)
  const avgBytesPerSec = bandwidthData.length > 0 
    ? totalBytes / bandwidthData.length 
    : 0
  const peakBytes = Math.max(...bandwidthData.map(d => d.bytes || 0), 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-text-muted">Real-time network flow overview</p>
        </div>
        <div className="flex items-center gap-4">
          <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
            wsConnected ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
          }`}>
            <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-400' : 'bg-red-400'}`} />
            <span>{wsConnected ? 'Live' : 'Offline'}</span>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Bandwidth"
          value={formatBytes(totalBytes)}
          icon={<DownloadIcon />}
          subtitle={`${formatNumber(bandwidthData.length)} data points`}
        />
        <StatCard
          title="Avg Throughput"
          value={`${formatBytes(avgBytesPerSec)}/s`}
          icon={<ActivityIcon />}
          subtitle={loading ? 'Loading...' : 'Real-time'}
        />
        <StatCard
          title="Peak Throughput"
          value={`${formatBytes(peakBytes)}/interval`}
          icon={<TrendingUpIcon />}
          subtitle={`Top talkers: ${topTalkers.length}`}
        />
        <StatCard
          title="Protocols Tracked"
          value={protocols.length.toString()}
          icon={<PieChartIcon />}
          subtitle={`Active: ${new Set(bandwidthData.map(d => d.protocol)).size}`}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Real-time Bandwidth Chart */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Real-time Bandwidth</CardTitle>
            <span className="text-xs text-text-muted">
              {wsConnected ? '🔴 Live' : '⚪ Historical'}
            </span>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={bandwidthData}>
                  <defs>
                    <linearGradient id="colorBandwidth" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--color-primary)" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="var(--color-primary)" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis 
                    dataKey="time" 
                    tickFormatter={(value) => formatTime(value)}
                    stroke="var(--color-text-muted)"
                    fontSize={11}
                    tickCount={8}
                  />
                  <YAxis 
                    tickFormatter={(value) => formatBytes(value) + '/s'}
                    stroke="var(--color-text-muted)"
                    fontSize={11}
                    tickCount={5}
                  />
                  <Tooltip 
                    formatter={(value: number) => [formatBytes(value), 'Bytes/sec']}
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-md)',
                    }}
                    labelFormatter={(time) => formatTime(time)}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="bytes" 
                    stroke="var(--color-primary)" 
                    fillOpacity={1} 
                    fill="url(#colorBandwidth)"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={!loading}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Protocol Distribution - Real-time */}
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

      {/* Bottom Row - Top Talkers Table with Real-time Updates */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Top Talkers (Real-time)</CardTitle>
            <span className="text-xs text-text-muted">
              Updated: {new Date().toLocaleTimeString()}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left text-text-muted text-sm">
                  <th className="pb-3 pr-4">Rank</th>
                  <th className="pb-3 pr-4">Source IP</th>
                  <th className="pb-3 pr-4">Country</th>
                  <th className="pb-3 pr-4">Bytes</th>
                  <th className="pb-3 pr-4">Packets</th>
                  <th className="pb-3 pr-4">% of Total</th>
                  <th className="pb-3 pr-4">Trend</th>
                </tr>
              </thead>
              <tbody>
                {topTalkers.slice(0, 15).map((talker, index) => {
                  const percentage = totalBytes > 0 ? (talker.value / totalBytes) * 100 : 0
                  const prevValue = bandwidthHistoryRef.current.get(talker.src_ip) || 0
                  const trend = talker.value > prevValue ? 'up' : talker.value < prevValue ? 'down' : 'stable'
                  
                  // Update history for next comparison
                  bandwidthHistoryRef.current.set(talker.src_ip, talker.value)
                  
                  return (
                    <tr key={talker.src_ip} className="border-b border-border/50 hover:bg-surface-hover transition-colors">
                      <td className="py-3 pr-4 font-medium text-text-muted">#{index + 1}</td>
                      <td className="py-3 pr-4 font-mono">{talker.src_ip}</td>
                      <td className="py-3 pr-4">
                        <span className="text-text-muted">—</span>
                      </td>
                      <td className="py-3 pr-4">{formatBytes(talker.value)}</td>
                      <td className="py-3 pr-4">{formatNumber(talker.packets || 0)}</td>
                      <td className="py-3 pr-4">
                        <div className="w-32 h-2 bg-border rounded-full overflow-hidden">
                          <div 
                            className={`h-full transition-all duration-500 ${trend === 'up' ? 'bg-green-500' : trend === 'down' ? 'bg-red-500' : 'bg-primary'}`} 
                            style={{ width: `${Math.min(percentage, 100).toFixed(1)}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-3 pr-4">
                        <span className={`inline-flex items-center gap-1 text-xs ${
                          trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'text-text-muted'
                        }`}>
                          {trend === 'up' && <span>↑</span>}
                          {trend === 'down' && <span>↓</span>}
                          {trend === 'stable' && <span>—</span>}
                        </span>
                      </td>
                    </tr>
                  )
                })}
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

function TrendingUpIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4 4-6-6" /></svg>
}

function PieChartIcon() {
  return <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.488 9A9.001 9.001 0 1113 20.945V13H3.055" /></svg>
}

function formatTime(time: string): string {
  try {
    return new Date(time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return time
  }
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

// CSS custom properties for chart colors
// Add to index.css: 
// :root { --chart-color-0: #3b82f6; --chart-color-1: #10b981; --chart-color-2: #f59e0b; --chart-color-3: #ef4444; --chart-color-4: #8b5cf6; --chart-color-5: #ec4899; --chart-color-6: #06b6d4; --chart-color-7: #84cc16; }