import { api } from '@/lib/api/client'
import type { KgContextDto, KgEdgeDto, KgNodeDto, KgSubgraphDto } from '@/lib/api/types'

export const graphApi = {
  listEntities: (nodeType: string) => api.get<KgNodeDto[]>(`/api/v1/graph/entities/${nodeType}`),
  getEntity: (nodeType: string, entityRef: string) =>
    api.get<KgNodeDto>(`/api/v1/graph/entities/${nodeType}/${entityRef}`),
  relationships: (fromId: string, toId: string) =>
    api.get<KgEdgeDto[]>('/api/v1/graph/relationships', { from_id: fromId, to_id: toId }),
  traverse: (
    nodeId: string,
    edgeType: string,
    opts: { reverse?: boolean; max_hops?: number; max_nodes?: number } = {},
  ) => api.get<KgNodeDto[]>('/api/v1/graph/traverse', { node_id: nodeId, edge_type: edgeType, ...opts }),
  shortestPath: (fromId: string, toId: string, opts: { edge_type?: string; max_depth?: number } = {}) =>
    api.get<{ nodes: KgNodeDto[]; meta: { connected: boolean } }>('/api/v1/graph/shortest-path', {
      from_id: fromId,
      to_id: toId,
      ...opts,
    }),
  timeline: (nodeId: string, edgeType?: string) =>
    api.get<KgEdgeDto[]>(`/api/v1/graph/timeline/${nodeId}`, { edge_type: edgeType }),
  atTime: (nodeId: string, asOf: string, opts: { depth?: number; max_nodes?: number } = {}) =>
    api.get<KgSubgraphDto>(`/api/v1/graph/at-time/${nodeId}`, { as_of: asOf, ...opts }),
  similar: (nodeId: string, nodeType: string, opts: { limit?: number; min_score?: number } = {}) =>
    api.get<Array<{ node: KgNodeDto; score: number }>>(`/api/v1/graph/similar/${nodeId}`, {
      node_type: nodeType,
      ...opts,
    }),
  context: (nodeId: string, opts: { depth?: number; max_nodes?: number } = {}) =>
    api.get<KgContextDto>(`/api/v1/graph/context/${nodeId}`, opts),
  neighborhood: (nodeId: string, opts: { depth?: number; edge_type?: string; max_nodes?: number } = {}) =>
    api.get<KgSubgraphDto>(`/api/v1/graph/neighborhood/${nodeId}`, opts),
  statistics: () => api.get<Record<string, unknown>>('/api/v1/graph/statistics'),
}
