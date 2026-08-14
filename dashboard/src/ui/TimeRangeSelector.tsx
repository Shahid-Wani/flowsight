import { useState, ChangeEvent } from 'react'

interface TimeRangeSelectorProps {
  value: string
  onChange: (value: string) => void
  className?: string
}

const TIME_RANGES = [
  { value: '-5m', label: 'Last 5 minutes' },
  { value: '-15m', label: 'Last 15 minutes' },
  { value: '-30m', label: 'Last 30 minutes' },
  { value: '-1h', label: 'Last hour' },
  { value: '-6h', label: 'Last 6 hours' },
  { value: '-12h', label: 'Last 12 hours' },
  { value: '-24h', label: 'Last 24 hours' },
  { value: '-7d', label: 'Last 7 days' },
]

export function TimeRangeSelector({ value, onChange, className = '' }: TimeRangeSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className={`relative ${className}`}>
      <button
        type="button"
        className="flex items-center gap-2 px-4 py-2 bg-surface border border-border rounded-lg text-sm font-medium hover:bg-surface-hover transition-colors"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      >
        <span>{TIME_RANGES.find(r => r.value === value)?.label || value}</span>
        <svg className="w-4 h-4 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <>
          <div 
            className="fixed inset-0 z-40" 
            onClick={() => setIsOpen(false)} 
            aria-hidden="true"
          />
          <div className="absolute right-0 z-50 mt-1 w-48 bg-surface border border-border rounded-lg shadow-lg py-1">
            {TIME_RANGES.map((range) => (
              <button
                key={range.value}
                type="button"
                className={`w-full px-4 py-2 text-left text-sm ${
                  value === range.value
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-text hover:bg-surface-hover'
                }`}
                onClick={() => {
                  onChange(range.value)
                  setIsOpen(false)
                }}
              >
                {range.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}