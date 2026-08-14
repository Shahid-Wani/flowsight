import { Card } from '../ui/Card'
import { TimeRangeSelector } from '../ui/TimeRangeSelector'

export function GeoMap() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Geo Map</h1>
          <p className="text-text-muted">Geographic visualization of network traffic</p>
        </div>
        <TimeRangeSelector value="-1h" onChange={() => {}} />
      </div>

      <Card className="h-96 flex items-center justify-center">
        <div className="text-center text-text-muted">
          <svg className="w-16 h-16 mx-auto mb-4 text-text-dim" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.303A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15l3-3m0 0l-3-3m3 3H9" />
          </svg>
          <h3 className="text-xl font-semibold mb-2">Geo Map Visualization</h3>
          <p className="text-text-muted">Interactive world map showing traffic origins and destinations</p>
          <div className="mt-6 p-4 bg-surface border border-border rounded-lg max-w-md mx-auto text-left text-sm">
            <p className="font-medium mb-2">Planned Features:</p>
            <ul className="space-y-1 text-text-muted">
              <li>• Source/destination country mapping</li>
              <li>• Traffic volume by region (choropleth)</li>
              <li>• Connection lines between countries</li>
              <li>• Real-time attack origin tracking</li>
              <li>• Drill-down to ASN/ISP level</li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  )
}