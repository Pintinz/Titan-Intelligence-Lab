import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SPORT_OPTIONS, type SportCode } from '@/lib/api/sports'

export function SportTabs({ value, onChange }: { value: SportCode; onChange: (code: SportCode) => void }) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as SportCode)}>
      <TabsList>
        {SPORT_OPTIONS.map((sport) => (
          <TabsTrigger key={sport.code} value={sport.code}>
            {sport.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
