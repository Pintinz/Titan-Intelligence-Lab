import { Fragment } from 'react'
import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'

export interface Breadcrumb {
  label: string
  to?: string
}

export function Breadcrumbs({ items, className }: { items: Breadcrumb[]; className?: string }) {
  return (
    <nav aria-label="Breadcrumb" className={cn('flex items-center text-sm', className)}>
      <ol className="flex items-center gap-1.5">
        {items.map((item, index) => {
          const isLast = index === items.length - 1
          return (
            <Fragment key={`${item.label}-${index}`}>
              {index > 0 && <ChevronRight className="h-3.5 w-3.5 text-text-muted" aria-hidden="true" />}
              <li>
                {item.to && !isLast ? (
                  <Link to={item.to} className="text-text-secondary hover:text-text-primary">
                    {item.label}
                  </Link>
                ) : (
                  <span className={isLast ? 'font-medium text-text-primary' : 'text-text-secondary'} aria-current={isLast ? 'page' : undefined}>
                    {item.label}
                  </span>
                )}
              </li>
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}
