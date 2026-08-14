import { Card } from '../ui/Card'
import { TimeRangeSelector } from '../ui/TimeRangeSelector'
import { Table } from '../ui/Table'
import { formatBytes } from '../utils/format'

interface TopTalker {
  src_ip: string
  value: number
}

export function TopTalkers() {
  // Placeholder - will connect to API
  const mockData: TopTalker[] = [
    { src_ip: '192.168.1.100', value: 1073741824 },
    { src_ip: '10.0.0.50', value: 536870912 },
    { src_ip: '172.16.0.25', value: 268435456 },
    { src_ip: '192.168.1.200', value: 134217728 },
    { src_ip: '10.0.1.10', value: 67108864 },
  ]

  const columns = [
    { key: 'rank', header: 'Rank', render: (row: TopTalker, index: number) => `#${index + 1}` },
    { key: 'src_ip', header: 'Source IP' },
    { key: 'bytes', header: 'Bytes', render: (row: TopTalker) => formatBytes(row.value) },
    { key: 'percentage', header: '% of Total', render: (row: TopTalker) => `${((row.value / 2080374784) * 100).toFixed(1)}%` },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Top Talkers</h1>
          <p className="text-text-muted">Source IPs by total bytes transmitted</p>
        </div>
        <TimeRangeSelector value="-1h" onChange={() => {}} />
      </div>

      <Card>
        <Table columns={columns} data={mockData} />
      </Card>
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}