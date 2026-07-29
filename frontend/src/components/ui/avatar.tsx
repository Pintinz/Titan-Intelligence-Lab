import type { ComponentProps } from 'react'
import * as AvatarPrimitive from '@radix-ui/react-avatar'
import { cn } from '@/lib/cn'

export function Avatar({ className, ...props }: ComponentProps<typeof AvatarPrimitive.Root>) {
  return (
    <AvatarPrimitive.Root
      className={cn('relative flex h-9 w-9 shrink-0 overflow-hidden rounded-full bg-bg-secondary', className)}
      {...props}
    />
  )
}

export function AvatarImage(props: ComponentProps<typeof AvatarPrimitive.Image>) {
  return <AvatarPrimitive.Image className="h-full w-full object-cover" {...props} />
}

export function AvatarFallback({ className, ...props }: ComponentProps<typeof AvatarPrimitive.Fallback>) {
  return (
    <AvatarPrimitive.Fallback
      className={cn('flex h-full w-full items-center justify-center text-xs font-medium text-text-secondary', className)}
      {...props}
    />
  )
}
