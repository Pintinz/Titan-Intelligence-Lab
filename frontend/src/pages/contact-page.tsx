import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, Controller } from 'react-hook-form'
import { z } from 'zod'
import { LifeBuoy, Building2, Crown, Handshake, Newspaper, ShieldAlert, Clock, MapPin } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, ContactCard } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/stores/toast-store'

const CHANNELS = [
  { icon: LifeBuoy, title: 'General Support', description: 'Questions about your account, subscription, or using the platform.', email: 'support@titaniq.ai', responseTime: 'Typically within 1 business day' },
  { icon: Building2, title: 'Business Enquiries', description: 'General business and commercial questions.', email: 'business@titaniq.ai', responseTime: 'Typically within 2 business days' },
  { icon: Crown, title: 'Enterprise Sales', description: 'API access, custom integrations, and enterprise agreements.', email: 'enterprise@titaniq.ai', responseTime: 'Typically within 1 business day' },
  { icon: Handshake, title: 'Partnership Requests', description: 'Data partnerships, integrations, and collaboration proposals.', email: 'partners@titaniq.ai', responseTime: 'Typically within 3 business days' },
  { icon: Newspaper, title: 'Media Requests', description: 'Press inquiries — see also our Press Kit for assets and boilerplate.', email: 'press@titaniq.ai', responseTime: 'Typically within 2 business days' },
  { icon: ShieldAlert, title: 'Security & Responsible Disclosure', description: 'Report a vulnerability under our good-faith disclosure policy.', email: 'security@titaniq.ai', responseTime: 'Acknowledged within 48 hours' },
]

const CATEGORY_EMAIL: Record<string, string> = {
  general: 'support@titaniq.ai',
  business: 'business@titaniq.ai',
  enterprise: 'enterprise@titaniq.ai',
  partnership: 'partners@titaniq.ai',
  media: 'press@titaniq.ai',
  security: 'security@titaniq.ai',
}

const contactSchema = z.object({
  category: z.string().min(1, 'Please select a category'),
  name: z.string().min(1, 'Your name is required'),
  email: z.string().email('Enter a valid email address'),
  message: z.string().min(10, 'Tell us a little more (at least 10 characters)'),
})

type ContactValues = z.infer<typeof contactSchema>

export default function ContactPage() {
  const [sent, setSent] = useState(false)
  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ContactValues>({ resolver: zodResolver(contactSchema), defaultValues: { category: 'general' } })

  function onSubmit(values: ContactValues) {
    const to = CATEGORY_EMAIL[values.category] ?? 'support@titaniq.ai'
    const subject = encodeURIComponent(`[TitanIQ Contact] ${values.category} — ${values.name}`)
    const body = encodeURIComponent(`${values.message}\n\n—\n${values.name}\n${values.email}`)
    window.location.href = `mailto:${to}?subject=${subject}&body=${body}`
    setSent(true)
    toast.success('Opening your email client', 'Complete the message in your mail app to reach our team.')
  }

  return (
    <>
      <Seo
        title="Contact TitanIQ"
        description="Reach TitanIQ's team for support, enterprise sales, partnerships, media, or security reporting."
        path="/contact"
      />
      <PageHero
        eyebrow="Contact"
        title="Talk to our team."
        description="Route your message to the right team below, or use the form to send us a note directly."
      />

      <Section>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {CHANNELS.map((channel) => (
            <ContactCard key={channel.title} {...channel} />
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <div className="grid gap-12 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <SectionHeading eyebrow="Details" title="Support hours & office" />
            <div className="space-y-5">
              <div className="flex gap-3">
                <Clock className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
                <div>
                  <p className="text-sm font-medium text-text-primary">Support hours</p>
                  <p className="mt-0.5 text-sm text-text-secondary">
                    Monday–Friday, 09:00–18:00 UTC. Security reports are monitored outside these hours.
                  </p>
                </div>
              </div>
              <div className="flex gap-3">
                <MapPin className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
                <div>
                  <p className="text-sm font-medium text-text-primary">Office</p>
                  <p className="mt-0.5 text-sm text-text-secondary">
                    Titan Intelligence Labs operates as a distributed-first team. Registered office details are
                    available on request during enterprise procurement — contact{' '}
                    <a href="mailto:enterprise@titaniq.ai" className="text-accent-primary hover:text-accent-primary-hover">
                      enterprise@titaniq.ai
                    </a>
                    .
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-border-default bg-bg-elevated p-6">
            <h3 className="font-display text-base font-semibold text-text-primary">Send a message</h3>
            <p className="mt-1 text-sm text-text-secondary">
              We'll open your email client with this message pre-filled and addressed to the right team.
            </p>
            <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-4" noValidate>
              <div className="space-y-1.5">
                <Label htmlFor="category">Category</Label>
                <Controller
                  control={control}
                  name="category"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger id="category" className="w-full">
                        <SelectValue placeholder="Select a category" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="general">General Support</SelectItem>
                        <SelectItem value="business">Business Enquiries</SelectItem>
                        <SelectItem value="enterprise">Enterprise Sales</SelectItem>
                        <SelectItem value="partnership">Partnership Requests</SelectItem>
                        <SelectItem value="media">Media Requests</SelectItem>
                        <SelectItem value="security">Security Reporting</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                />
                {errors.category && <p className="text-xs text-danger">{errors.category.message}</p>}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="name">Name</Label>
                  <Input id="name" aria-invalid={!!errors.name} {...register('name')} />
                  {errors.name && <p className="text-xs text-danger">{errors.name.message}</p>}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" aria-invalid={!!errors.email} {...register('email')} />
                  {errors.email && <p className="text-xs text-danger">{errors.email.message}</p>}
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="message">Message</Label>
                <Textarea id="message" rows={5} aria-invalid={!!errors.message} {...register('message')} />
                {errors.message && <p className="text-xs text-danger">{errors.message.message}</p>}
              </div>

              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {sent ? 'Open email client again' : 'Send message'}
              </Button>
            </form>
          </div>
        </div>
      </Section>
    </>
  )
}
