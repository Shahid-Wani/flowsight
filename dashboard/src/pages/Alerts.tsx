import { Card } from '../ui/Card'
import { TimeRangeSelector } from '../ui/TimeRangeSelector'
import { Table } from '../ui/Table'
import { Badge } from '../ui/Badge'
import { Alert } from '../../types'

export function Alerts() {
  const mockAlerts: Alert[] = [
    {
      rule_name: 'high_bandwidth',
      severity: 'critical',
      message: 'Threshold exceeded: bytes > 100000000 (value: 152345678)',
      flow_data: { src_ip: '192.168.1.100', dst_ip: '10.0.0.50', bytes: 152345678, packets: 125000 },
      timestamp: '2024-01-15T10:30:45.123Z',
      acknowledged: false,
    },
    {
      rule_name: 'many_packets',
      severity: 'warning',
      message: 'Threshold exceeded: packets > 10000 (value: 15234)',
      flow_data: { src_ip: '10.0.0.50', dst_ip: '192.168.1.100', bytes: 52345678, packets: 15234 },
      timestamp: '2024-01-15T10:25:12.456Z',
      acknowledged: true,
    },
    {
      rule_name: 'high_bandwidth',
      severity: 'warning',
      message: 'Threshold exceeded: bytes > 100000000 (value: 112345678)',
      flow_data: { src_ip: '172.16.0.25', dst_ip: '192.168.1.200', bytes: 112345678, packets: 98765 },
      timestamp: '2024-01-15T10:15:33.789Z',
      acknowledged: false,
    },
    {
      rule_name: 'long_duration',
      severity: 'info',
      message: 'Threshold exceeded: duration > 3600 (value: 4200)',
      flow_data: { src_ip: '192.168.1.200', dst_ip: '10.0.1.10', bytes: 67108864, packets: 45000 },
      timestamp: '2024-01-15T10:05:21.234Z',
      acknowledged: true,
    },
  ]

  const columns = [
    { key: 'severity', header: 'Severity', render: (row: Alert) => (
      <Badge variant={row.severity}>{row.severity.toUpperCase()}</Badge>
    )},
    { key: 'rule_name', header: 'Rule' },
    { key: 'message', header: 'Message', className: 'max-w-md truncate' },
    { key: 'src_ip', header: 'Source IP', render: (row: Alert) => row.flow_data.src_ip },
    { key: 'dst_ip', header: 'Dest IP', render: (row: Alert) => row.flow_data.dst_ip },
    { key: 'timestamp', header: 'Time', render: (row: Alert) => new Date(row.timestamp).toLocaleString() },
    { key: 'acknowledged', header: 'Status', render: (row: Alert) => (
      <Badge variant={row.acknowledged ? 'success' : 'warning'}>
        {row.acknowledged ? 'Acknowledged' : 'Pending'}
      </Badge>
    )},
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Alerts</h1>
          <p className="text-text-muted">Threshold-based anomaly alerts</p>
        </div>
        <TimeRangeSelector value="-1h" onChange={() => {}} />
      </div>

      <Card>
        <Table 
          columns={columns} 
          data={mockAlerts} 
          striped
          hoverable
        />
      </Card>
    </div>
  )
}

function Badge({ variant = 'default', children }: { variant?: 'default' | 'success' | 'warning' | 'danger' | 'info'; children: React.ReactNode }) {
  const variants = {
    default: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
    success: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    danger: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${variants[variant]}`}>
      {children}
    </span>
  )
}