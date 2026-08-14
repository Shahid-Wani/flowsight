import { Card } from '../ui/Card'
import { TimeRangeSelector } from '../ui/TimeRangeSelector'
import { Table } from '../ui/Table'
import { formatBytes } from '../utils/format'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

interface ProtocolData {
  protocol: string
  bytes: number
}

export function ProtocolDistribution() {
  const mockData: ProtocolData[] = [
    { protocol: 'TCP', bytes: 1200000000 },
    { protocol: 'UDP', bytes: 500000000 },
    { protocol: 'ICMP', bytes: 50000000 },
    { protocol: 'Other', bytes: 25000000 },
  ]

  const total = mockData.reduce((sum, d) => sum + d.bytes, 0)

  const columns = [
    { key: 'protocol', header: 'Protocol' },
    { key: 'bytes', header: 'Bytes', render: (row: ProtocolData) => formatBytes(row.bytes) },
    { key: 'percentage', header: '%', render: (row: ProtocolData) => `${((row.bytes / total) * 100).toFixed(1)}%` },
  ]

  const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Protocol Distribution</h1>
          <p className="text-text-muted">Traffic breakdown by network protocol</p>
        </div>
        <TimeRangeSelector value="-1h" onChange={() => {}} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <h3 className="text-lg font-semibold">Distribution by Bytes</h3>
          </CardHeader>
          <CardContent>
            <div className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={mockData}
                    cx="50%"
                    cy="50%"
                    innerRadius={80}
                    outerRadius={140}
                    paddingAngle={3}
                    dataKey="bytes"
                    nameKey="protocol"
                    label={({ protocol, percent }) => `${protocol} ${(percent * 100).toFixed(1)}%`}
                  >
                    {mockData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => [formatBytes(value), 'Bytes']} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h3 className="text-lg font-semibold">Protocol Details</h3>
          </CardHeader>
          <CardContent>
            <Table
              columns={[
                { key: 'protocol', header: 'Protocol' },
                { key: 'bytes', header: 'Bytes', render: (row: ProtocolData) => formatBytes(row.bytes) },
                { key: 'percentage', header: '%', render: (row: ProtocolData) => `${((row.bytes / total) * 100).toFixed(1)}%` },
              ]}
              data={mockData}
            />
          </CardContent>
        </Card>
      </div>
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