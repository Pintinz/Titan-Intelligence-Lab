import { z } from 'zod'

// Trimmed before the format check — a stray leading/trailing space from autofill or a
// copy-paste would otherwise fail validation with a confusing "invalid email" for an email that
// looks correct at a glance, a real source of registration/login friction.
const emailField = z.string().trim().email('Enter a valid email address')

export const loginSchema = z.object({
  email: emailField,
  password: z.string().min(1, 'Password is required'),
})
export type LoginValues = z.infer<typeof loginSchema>

export const signupSchema = z
  .object({
    email: emailField,
    password: z.string().min(8, 'Use at least 8 characters'),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })
export type SignupValues = z.infer<typeof signupSchema>

export const magicLinkSchema = z.object({
  email: emailField,
})
export type MagicLinkValues = z.infer<typeof magicLinkSchema>

export const forgotPasswordSchema = magicLinkSchema
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>

export const resetPasswordSchema = z
  .object({
    password: z.string().min(8, 'Use at least 8 characters'),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>
