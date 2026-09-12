import { ReactNode } from 'react'

interface StatCardProps {
  title: string
  value: string
  icon: ReactNode
  subtitle?: string
  trend?: string
  trendUp?: boolean
  className?: string
}

export function StatCard({ title, value, icon, subtitle, trend, trendUp, className = '' }: StatCardProps) {
  return (
    <div className={`bg-surface border border-border rounded-lg p-6 ${className}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-text-muted">{title}</p>
          <p className="mt-1 text-3xl font-bold">{value}</p>
          {subtitle && (
            <p className="mt-1 text-xs text-text-muted">{subtitle}</p>
          )}
          {trend && (
            <p className={`mt-2 text-sm font-medium ${trendUp ? 'text-success' : 'text-danger'}`}>
              {trend}
            </p>
          )}
        </div>
        <div className="p-3 bg-primary/10 rounded-lg text-primary">
          {icon}
        </div>
      </div>
    </div>
  )
}