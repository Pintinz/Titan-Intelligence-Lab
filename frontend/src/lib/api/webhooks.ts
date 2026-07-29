import { api } from '@/lib/api/client'
import type { WebhookDeliveryDto, WebhookEndpointDto } from '@/lib/api/types'

export const webhooksApi = {
  registerEndpoint: (organizationId: string, url: string, subscribedEvents: string[] = ['*']) =>
    api.post<WebhookEndpointDto & { signing_secret: string }>('/api/v1/webhooks/endpoints', {
      organization_id: organizationId,
      url,
      subscribed_events: subscribedEvents,
    }),
  listEndpoints: (organizationId: string) =>
    api.get<WebhookEndpointDto[]>(`/api/v1/webhooks/organizations/${organizationId}/endpoints`),
  rotateSecret: (endpointId: string) =>
    api.post<WebhookEndpointDto & { signing_secret: string }>(`/api/v1/webhooks/endpoints/${endpointId}/rotate-secret`),
  deactivateEndpoint: (endpointId: string) =>
    api.delete<{ deactivated: boolean }>(`/api/v1/webhooks/endpoints/${endpointId}`),
  listDeliveries: (endpointId: string) =>
    api.get<WebhookDeliveryDto[]>(`/api/v1/webhooks/endpoints/${endpointId}/deliveries`),
}
