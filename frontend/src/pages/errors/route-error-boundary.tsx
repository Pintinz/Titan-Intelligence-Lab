import { isRouteErrorResponse, useRouteError } from 'react-router-dom'
import ServerErrorPage from './server-error-page'
import NotFoundPage from './not-found-page'

/** Router-level `errorElement` — catches render/loader errors that escape a route's own tree. */
export function RouteErrorBoundary() {
  const error = useRouteError()

  if (isRouteErrorResponse(error) && error.status === 404) {
    return <NotFoundPage />
  }

  const message = error instanceof Error ? error.message : undefined
  return <ServerErrorPage message={message} />
}
