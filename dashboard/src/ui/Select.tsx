import { ReactNode } from 'react'

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  helperText?: string
  options: Array<{ value: string; label: string }>
}

export function Select({ 
  label, 
  error, 
  helperText, 
  options, 
  className = '', 
  id,
  ...props 
}: SelectProps) {
  const selectId = id || label?.toLowerCase().replace(/\s+/g, '-')
  
  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={selectId} className="block text-sm font-medium text-text">
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={`w-full px-3 py-2 bg-background border rounded-lg text-text appearance-none bg-no-repeat bg-right pr-10 
          ${error 
            ? 'border-danger focus:ring-danger focus:border-danger' 
            : 'border-border focus:ring-primary focus:border-primary'}
          ${className}`}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={error ? `${selectId}-error` : helperText ? `${selectId}-helper` : undefined}
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={`${selectId}-error`} className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      {helperText && !error && (
        <p id={`${selectId}-helper`} className="text-sm text-text-muted">
          {helperText}
        </p>
      )}
    </div>
  )
}