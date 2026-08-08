/** Real country name → flag emoji, covering the countries that actually appear in TitanIQ's
 * sports data today (England, Germany) plus the broader common set international sports
 * competitions cover. Backend only ever returns a free-text country name, never an ISO code, so
 * this is a decorative accompaniment to the real name text — never a replacement for it, and
 * never guessed for a name outside this map (dev data's placeholder "Mockland" correctly renders
 * with no flag at all rather than a wrong or invented one). */
const COUNTRY_FLAGS: Record<string, string> = {
  England: '🇬🇧',
  Scotland: '🏴',
  Wales: '🏴',
  'Northern Ireland': '🇬🇧',
  'United Kingdom': '🇬🇧',
  Germany: '🇩🇪',
  Spain: '🇪🇸',
  Italy: '🇮🇹',
  France: '🇫🇷',
  Portugal: '🇵🇹',
  Netherlands: '🇳🇱',
  Belgium: '🇧🇪',
  Turkey: '🇹🇷',
  Greece: '🇬🇷',
  Austria: '🇦🇹',
  Switzerland: '🇨🇭',
  Russia: '🇷🇺',
  Ukraine: '🇺🇦',
  Poland: '🇵🇱',
  'United States': '🇺🇸',
  USA: '🇺🇸',
  Canada: '🇨🇦',
  Mexico: '🇲🇽',
  Brazil: '🇧🇷',
  Argentina: '🇦🇷',
  Japan: '🇯🇵',
  'South Korea': '🇰🇷',
  China: '🇨🇳',
  Australia: '🇦🇺',
}

export function countryFlag(country: string | null | undefined): string | null {
  if (!country) return null
  return COUNTRY_FLAGS[country] ?? null
}
