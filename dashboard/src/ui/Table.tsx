import { ReactNode } from 'react'

interface TableProps<T> {
  columns: Array<{
    key: string
    header: string
    render?: (row: T, index: number) => ReactNode
    className?: string
    sortable?: boolean
  }>
  data: T[]
  striped?: boolean
  hoverable?: boolean
  className?: string
  onRowClick?: (row: T, index: number) => void
  onHeaderClick?: (key: string) => void
}

export function Table<T>({
  columns,
  data,
  striped = false,
  hoverable = false,
  className = '',
  onRowClick,
  onHeaderClick,
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
                {col.sortable && onHeaderClick ? (
                  <button
                    type="button"
                    onClick={() => onHeaderClick(col.key)}
                    className="inline-flex items-center gap-1 hover:text-text transition-colors"
                  >
                    {col.header}
                    <span className="text-text-dim">↕</span>
                  </button>
                ) : (
                  col.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              onClick={onRowClick ? () => onRowClick(row, rowIndex) : undefined}
              className={`border-b border-border/50 ${striped && rowIndex % 2 === 1 ? 'bg-surface-hover/50' : ''} ${hoverable ? 'hover:bg-surface-hover transition-colors' : ''} ${onRowClick ? 'cursor-pointer' : ''}`}
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
