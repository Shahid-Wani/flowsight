import { Card } from '../ui/Card'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import { Button } from '../ui/Button'

export function Settings() {
  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-text-muted">Configure FlowSight dashboard and API connection</p>
      </div>

      <Card>
        <CardHeader>
          <h3 className="text-lg font-semibold">API Configuration</h3>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input
              label="API Base URL"
              placeholder="http://localhost:8000"
              defaultValue="http://localhost:8000"
            />
            <Input
              label="WebSocket URL"
              placeholder="ws://localhost:8000/api/v1/ws/live"
              defaultValue="ws://localhost:8000/api/v1/ws/live"
            />
          </div>
          <Input
            label="API Key (Optional)"
            placeholder="Enter API key if required"
            type="password"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h3 className="text-lg font-semibold">Dashboard Preferences</h3>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Select
              label="Default Time Range"
              options={[
                { value: '-5m', label: 'Last 5 minutes' },
                { value: '-15m', label: 'Last 15 minutes' },
                { value: '-1h', label: 'Last hour' },
                { value: '-6h', label: 'Last 6 hours' },
                { value: '-24h', label: 'Last 24 hours' },
              ]}
              defaultValue="-1h"
            />
            <Select
              label="Auto Refresh Interval"
              options={[
                { value: 'off', label: 'Off' },
                { value: '10s', label: '10 seconds' },
                { value: '30s', label: '30 seconds' },
                { value: '1m', label: '1 minute' },
                { value: '5m', label: '5 minutes' },
              ]}
              defaultValue="30s"
            />
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-border text-primary focus:ring-primary" />
              <span>Enable dark mode</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-border text-primary focus:ring-primary" />
              <span>Show real-time animations</span>
            </label>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h3 className="text-lg font-semibold">Alert Notifications</h3>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-border text-primary focus:ring-primary" />
              <span>Enable browser notifications</span>
            </label>
          </div>
          <Input
            label="Webhook URL (for external alerts)"
            placeholder="https://your-webhook-url.com/alerts"
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Select
              label="Minimum Severity"
              options={[
                { value: 'info', label: 'Info' },
                { value: 'warning', label: 'Warning' },
                { value: 'critical', label: 'Critical only' },
              ]}
              defaultValue="warning"
            />
            <Select
              label="Notification Sound"
              options={[
                { value: 'default', label: 'Default' },
                { value: 'alert', label: 'Alert' },
                { value: 'chime', label: 'Chime' },
                { value: 'none', label: 'None' },
              ]}
              defaultValue="default"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h3 className="text-lg font-semibold">Data Retention</h3>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Select
              label="Flow Data Retention"
              options={[
                { value: '1d', label: '1 day' },
                { value: '7d', label: '7 days' },
                { value: '30d', label: '30 days' },
                { value: '90d', label: '90 days' },
              ]}
              defaultValue="7d"
            />
            <Select
              label="Alert History Retention"
              options={[
                { value: '7d', label: '7 days' },
                { value: '30d', label: '30 days' },
                { value: '90d', label: '90 days' },
                { value: '365d', label: '1 year' },
              ]}
              defaultValue="90d"
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-4 pt-4 border-t border-border">
        <Button variant="secondary">Cancel</Button>
        <Button>Save Settings</Button>
      </div>
    </div>
  )
}