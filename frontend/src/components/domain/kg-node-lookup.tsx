import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { toast } from '@/stores/toast-store'

export function KgNodeLookup() {
  const [nodeType, setNodeType] = useState('team')
  const [entityRef, setEntityRef] = useState('')
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleLookup() {
    setLoading(true)
    try {
      const node = await adminPlatformApi.kgNode(nodeType, entityRef)
      setResult(node)
    } catch (error) {
      toast.danger('Lookup failed', error instanceof Error ? error.message : undefined)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>KG node lookup</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="kg-node-type">Node type</Label>
            <Input id="kg-node-type" value={nodeType} onChange={(e) => setNodeType(e.target.value)} className="w-32" />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="kg-entity-ref">Entity ref</Label>
            <Input id="kg-entity-ref" value={entityRef} onChange={(e) => setEntityRef(e.target.value)} className="w-48" />
          </div>
          <Button size="sm" disabled={!entityRef} loading={loading} onClick={handleLookup}>
            Look up
          </Button>
        </div>
        {result && <KeyValueGrid data={result} />}
      </CardContent>
    </Card>
  )
}
