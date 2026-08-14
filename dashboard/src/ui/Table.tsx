import { ReactNode } from 'react'

interface TableProps<T> {
  columns: Array<{
    key: string
    header: string
    render?: (row: T, index: number) => ReactNode
    className?: string
  }>
  data: T[]
  striped?: boolean
  hoverable?: boolean
  className?: string
}

export function Table<T>({ 
  columns, 
  data, 
  striped = false, 
  hoverable = false, 
  className = '' 
}: TableProps<T>) {
  if (data.length === 0) {
    return (
      <div className="text-center py-12 text-text-muted">
        No data available
      </div>
    )
  }

  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-text-muted font-medium">
            {columns.map((col) => (
              <th key={col.key} className={`pb-3 pr-4 ${col.className || ''}`}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIndex) => (
            <tr 
              key={rowIndex}
              className={`border-b border-border/50 ${striped && rowIndex % 2 === 1 ? 'bg-surface-hover/50' : ''} ${hoverable ? 'hover:bg-surface-hover transition-colors' : ''}`}
            >
              {columns.map((col) => (
                <td key={col.key} className={`py-3 pr-4 ${col.className || ''}`}>
                  {col.render ? col.render(row as T, rowIndex) : (row as any)[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}