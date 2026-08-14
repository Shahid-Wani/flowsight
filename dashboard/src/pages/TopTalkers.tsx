import { useState, useEffect, useCallback } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card'
import { Table } from '../ui/Table'
import { TimeRangeSelector } from '../ui/TimeRangeSelector'
import { Badge } from '../ui/Badge'
import { useWebSocket } from '../hooks/useWebSocket'
import { formatBytes, formatNumber } from '../utils/format'

interface TopTalker {
  src_ip: string
  dst_ip?: string
  value: number
  packets?: number
  protocol?: number
  country_code?: string
  asn?: number
  asn_org?: string
}

interface WSMessage {
  type: string
  data: any
}

export function TopTalkers() {
  const [topTalkers, setTopTalkers] = useState<TopTalker[]>([])
  const [timeRange, setTimeRange] = useState('-1h')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'value', direction: 'desc' })
  const [selectedTalker, setSelectedTalker] = useState<TopTalker | null>(null)

  const { isConnected, lastMessage } = useWebSocket('/api/v1/ws/live')

  // Handle WebSocket messages for real-time updates
  useEffect(() => {
    if (lastMessage) {
      try {
        const message: WSMessage = JSON.parse(lastMessage.data)
        if (message.type === 'top_talkers_update' && Array.isArray(message.data)) {
          // Merge with existing data, keeping sort order
          setTopTalkers(prev => {
            const newMap = new Map(message.data.map(t => [t.src_ip, t]))
            return prev.map(t => newMap.get(t.src_ip) || t)
          })
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
      const res = await fetch(`/api/v1/top-talkers?start=${timeRange}&stop=now&limit=50`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setTopTalkers(data.talkers || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch top talkers')
    } finally {
      setLoading(false)
    }
  }, [timeRange])

  useEffect(() => {
    fetchData()
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

  const sortedTalkers = [...topTalkers].sort((a, b) => {
    const aVal = (a as any)[sortConfig.key]
    const bVal = (b as any)[sortConfig.key]
    if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1
    if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1
    return 0
  })

  const columns = [
    { 
      key: 'rank', 
      header: 'Rank', 
      render: (_: TopTalker, index: number) => `#${index + 1}` 
    },
    { 
      key: 'src_ip', 
      header: 'Source IP', 
      sortable: true,
      render: (row: TopTalker) => (
        <span className="font-mono text-sm">{row.src_ip}</span>
      )
    },
    { 
      key: 'country_code', 
      header: 'Country', 
      render: (row: TopTalker) => 
        row.country_code ? (
          <span className="flex items-center gap-1">
            <span className="text-lg">{getCountryFlag(row.country_code)}</span>
            <span>{row.country_code}</span>
          </span>
        ) : <span className="text-text-muted">—</span>
    },
    { 
      key: 'asn_org', 
      header: 'ASN / Org', 
      render: (row: TopTalker) => 
        row.asn_org ? (
          <span className="text-sm truncate max-w-[200px]" title={row.asn_org}>
            AS{row.asn}: {row.asn_org}
          </span>
        ) : <span className="text-text-muted">—</span>
    },
    { 
      key: 'value', 
      header: 'Bytes', 
      sortable: true,
      render: (row: TopTalker) => (
        <span className="font-mono">{formatBytes(row.value)}</span>
      )
    },
    { 
      key: 'packets', 
      header: 'Packets', 
      sortable: true,
      render: (row: TopTalker) => 
        row.packets ? <span className="font-mono">{formatNumber(row.packets)}</span> : <span className="text-text-muted">—</span>
    },
    { 
      key: 'protocol', 
      header: 'Proto', 
      render: (row: TopTalker) => 
        row.protocol ? <Badge variant="info">{getProtocolName(row.protocol)}</Badge> : <span className="text-text-muted">—</span>
    },
    { 
      key: 'actions', 
      header: 'Actions', 
      render: (row: TopTalker) => (
        <button
          onClick={() => setSelectedTalker(row)}
          className="text-primary hover:underline text-sm"
        >
          Details
        </button>
      )
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Top Talkers</h1>
          <p className="text-text-muted">Source IPs by total bytes transmitted</p>
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

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={fetchData} className="text-sm underline">Retry</button>
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Top Talkers by Bytes</CardTitle>
          <div className="flex items-center gap-2 text-sm text-text-muted">
            <span>{topTalkers.length} talkers</span>
            <span>•</span>
            <span>Updated: {new Date().toLocaleTimeString()}</span>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-12 text-text-muted">
              <div className="animate-spin inline-block w-8 h-8 border-4 border-primary border-t-transparent rounded-full mb-2 mx-auto" />
              <p>Loading top talkers...</p>
            </div>
          ) : (
            <Table 
              columns={columns} 
              data={sortedTalkers} 
              striped
              hoverable
              onRowClick={(row) => setSelectedTalker(row)}
            />
          )}
        </CardContent>
      </Card>

      {selectedTalker && (
        <TalkerDetailModal 
          talker={selectedTalker} 
          onClose={() => setSelectedTalker(null)} 
        />
      )}
    </div>
  )
}

function TalkerDetailModal({ talker, onClose }: { talker: TopTalker; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-surface border border-border rounded-lg shadow-lg max-w-md w-full max-h-[80vh] overflow-y-auto">
        <div className="p-6 border-b border-border flex items-center justify-between">
          <h3 className="text-lg font-semibold">Talker Details</h3>
          <button onClick={onClose} className="text-text-muted hover:text-text p-1">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="p-6 space-y-4">
          <div className="flex items-center gap-3 p-4 bg-background rounded-lg">
            <span className="text-3xl font-mono text-primary">{talker.src_ip}</span>
            {talker.country_code && (
              <span className="text-2xl">{getCountryFlag(talker.country_code)}</span>
            )}
          </div>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-text-muted">Total Bytes</dt>
              <dd className="font-mono font-semibold">{formatBytes(talker.value)}</dd>
            </div>
            {talker.packets && (
              <div className="flex justify-between">
                <dt className="text-text-muted">Packets</dt>
                <dd className="font-mono">{formatNumber(talker.packets)}</dd>
              </div>
            )}
            {talker.protocol && (
              <div className="flex justify-between">
                <dt className="text-text-muted">Protocol</dt>
                <dd><Badge variant="info">{getProtocolName(talker.protocol)}</Badge></dd>
              </div>
            )}
            {talker.country_code && (
              <div className="flex justify-between">
                <dt className="text-text-muted">Country</dt>
                <dd className="flex items-center gap-2">
                  <span className="text-lg">{getCountryFlag(talker.country_code)}</span>
                  <span>{talker.country_code}</span>
                </dd>
              </div>
            )}
            {talker.asn && (
              <div className="flex justify-between">
                <dt className="text-text-muted">ASN</dt>
                <dd className="font-mono">AS{talker.asn}</dd>
              </div>
            )}
            {talker.asn_org && (
              <div className="flex justify-between">
                <dt className="text-text-muted">Organization</dt>
                <dd className="truncate max-w-[200px]">{talker.asn_org}</dd>
              </div>
            )}
          </dl>
        </div>
        <div className="p-6 border-t border-border flex justify-end">
          <button onClick={onClose} className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-hover transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

function getCountryFlag(code: string): string {
  if (!code || code.length !== 2) return '🏳️'
  const offset = 127397 // 0x1F1E6 - 'A'
  return String.fromCodePoint(...code.toUpperCase().split('').map(c => c.charCodeAt(0) + offset))
}

function getProtocolName(proto: number): string {
  const protocols: Record<number, string> = {
    1: 'ICMP', 6: 'TCP', 17: 'UDP', 2: 'IGMP', 41: 'IPv6', 47: 'GRE', 50: 'ESP', 51: 'AH', 58: 'ICMPv6', 89: 'OSPF', 132: 'SCTP'
  }
  return protocols[proto] || `Proto ${proto}`
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