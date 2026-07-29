import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Newspaper } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { intelligenceApi } from '@/lib/api/intelligence'

export default function NewsCenterPage() {
  const [query, setQuery] = useState('')

  const newsQuery = useQuery({
    queryKey: ['intelligence', 'news', query],
    queryFn: () => intelligenceApi.searchNews({ query: query || undefined, limit: 30 }),
  })

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'News Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">News Center</h1>
      </div>

      <Input
        placeholder="Search news…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="max-w-sm"
      />

      {newsQuery.isLoading && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {newsQuery.isError && <ErrorState description="Could not load news." onRetry={() => newsQuery.refetch()} />}

      {newsQuery.data && newsQuery.data.length === 0 && (
        <EmptyState icon={<Newspaper className="h-6 w-6" />} title="No articles found" />
      )}

      <div className="flex flex-col gap-3">
        {newsQuery.data?.map((article) => (
          <Link key={article.id} to={`/app/news/${article.id}`}>
            <Card className="transition-colors hover:border-border-strong">
              <CardHeader>
                <CardTitle className="text-base">{article.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-text-muted">
                {new Date(article.published_at).toLocaleString()}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
