import { useEffect } from 'react'

interface SeoProps {
  title: string
  description: string
  /** Defaults to `${title} — TitanIQ` unless title already contains the brand name. */
  path?: string
  image?: string
  type?: 'website' | 'article'
  noindex?: boolean
}

const SITE_NAME = 'TitanIQ'
const SITE_URL = 'https://titaniq.ai'
const DEFAULT_IMAGE = '/og-image.png'

function setMeta(attr: 'name' | 'property', key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function setLink(rel: string, href: string) {
  let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`)
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', rel)
    document.head.appendChild(el)
  }
  el.setAttribute('href', href)
}

/**
 * Per-page document head manager — no react-helmet dependency, just direct DOM writes on mount.
 * Tags persist between route changes (SPA), so every page must call this to keep title/meta
 * accurate; nothing resets it automatically between navigations.
 */
export function Seo({ title, description, path = '', image = DEFAULT_IMAGE, type = 'website', noindex = false }: SeoProps) {
  useEffect(() => {
    const fullTitle = title.includes(SITE_NAME) ? title : `${title} — ${SITE_NAME}`
    document.title = fullTitle

    const url = `${SITE_URL}${path}`
    const absoluteImage = image.startsWith('http') ? image : `${SITE_URL}${image}`

    setMeta('name', 'description', description)
    setMeta('name', 'robots', noindex ? 'noindex, nofollow' : 'index, follow')

    setMeta('property', 'og:title', fullTitle)
    setMeta('property', 'og:description', description)
    setMeta('property', 'og:type', type)
    setMeta('property', 'og:url', url)
    setMeta('property', 'og:image', absoluteImage)
    setMeta('property', 'og:site_name', SITE_NAME)

    setMeta('name', 'twitter:card', 'summary_large_image')
    setMeta('name', 'twitter:title', fullTitle)
    setMeta('name', 'twitter:description', description)
    setMeta('name', 'twitter:image', absoluteImage)
    setMeta('name', 'twitter:site', '@titaniq')

    setLink('canonical', url)
  }, [title, description, path, image, type, noindex])

  return null
}

/** JSON-LD structured data injector — pass a schema.org object, it's serialized and attached. */
export function StructuredData({ schema }: { schema: Record<string, unknown> }) {
  useEffect(() => {
    const script = document.createElement('script')
    script.type = 'application/ld+json'
    script.textContent = JSON.stringify(schema)
    script.dataset.titaniqStructuredData = 'true'
    document.head.appendChild(script)
    return () => {
      script.remove()
    }
  }, [schema])

  return null
}
