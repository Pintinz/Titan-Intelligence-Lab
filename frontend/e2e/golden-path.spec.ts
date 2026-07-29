import { expect, test } from '@playwright/test'

/**
 * Deliberately does NOT perform real Supabase sign-ups/logins — that would leave residual
 * `auth.users` rows in the live project on every CI run with no way to clean them up from
 * within a Playwright process (no service-role access here, unlike the interactive
 * verification passes done earlier against the live project). These tests cover what's safely
 * repeatable: public page rendering, navigation, client-side validation, and the auth guard.
 */

test('landing page renders the product identity and a sign-in path', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle(/TitanIQ/)
  await expect(page.getByRole('heading', { name: 'TitanIQ' })).toBeVisible()
  await page.getByRole('link', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/login$/)
})

test('login page renders all expected entry points', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByRole('button', { name: 'Continue with Google' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Continue with GitHub' })).toBeVisible()
  await expect(page.getByLabel('Email')).toBeVisible()
  await expect(page.getByLabel('Password')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Sign up' })).toBeVisible()
})

test('login form shows a client-side validation error for an invalid email', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('not-an-email')
  await page.getByLabel('Password').fill('irrelevant')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('Enter a valid email address')).toBeVisible()
})

test('signup page renders and links back to sign in', async ({ page }) => {
  await page.goto('/signup')
  await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible()
  await page.getByRole('link', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/login$/)
})

test('unauthenticated users are redirected away from /app', async ({ page }) => {
  await page.goto('/app')
  await expect(page).toHaveURL(/\/login$/)
})

test('theme toggle on the login page is unaffected by the app-shell-only toggle', async ({ page }) => {
  // Sanity check that the public auth pages don't crash without an app-shell context —
  // ThemeToggle only renders inside the authenticated AppShell (Topbar), by design.
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'Sign in to TitanIQ' })).toBeVisible()
})
