import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

const fieldClass = cn(
  'w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted',
  'transition-colors hover:border-border-strong focus-visible:border-accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40',
  'disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border-default',
)

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(fieldClass, className)} {...props} />
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(fieldClass, 'min-h-24 resize-y', className)} {...props} />
}
