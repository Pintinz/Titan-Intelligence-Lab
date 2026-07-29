import { Link } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import type { CompetitionSummaryDto } from '@/lib/api/types'

export function CompetitionCard({
  competition,
  sportSlug,
}: {
  competition: CompetitionSummaryDto
  sportSlug: string
}) {
  return (
    <Link to={`/app/${sportSlug}/competitions/${competition.id}`}>
      <Card className="h-full transition-colors hover:border-border-strong">
        <div className="flex flex-col gap-1 p-4">
          <p className="truncate font-display text-sm font-semibold text-text-primary">{competition.name}</p>
          <p className="truncate text-xs text-text-muted">
            {[competition.type, competition.country].filter(Boolean).join(' · ')}
          </p>
        </div>
      </Card>
    </Link>
  )
}
