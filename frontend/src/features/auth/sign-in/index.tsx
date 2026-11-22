import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { microsoftSignInUrl } from '@/lib/session'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { PasswordInput } from '@/components/password-input'
import { AuthLayout } from '../auth-layout'

function MicrosoftLogo() {
  return (
    <svg viewBox='0 0 21 21' className='size-4' aria-hidden='true'>
      <rect x='1' y='1' width='9' height='9' fill='#f25022' />
      <rect x='11' y='1' width='9' height='9' fill='#7fba00' />
      <rect x='1' y='11' width='9' height='9' fill='#00a4ef' />
      <rect x='11' y='11' width='9' height='9' fill='#ffb900' />
    </svg>
  )
}

function safeRedirect(redirect?: string) {
  if (!redirect) return '/'
  try {
    const url = new URL(redirect, window.location.origin)
    return url.origin === window.location.origin
      ? url.pathname + url.search
      : '/'
  } catch {
    return '/'
  }
}

export function SignIn() {
  const { t } = useTranslation()
  const { redirect, error } = useSearch({ from: '/(auth)/sign-in' })
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(
    error
      ? t(`auth.error.${error}`, { defaultValue: t('auth.error.generic') })
      : null
  )
  const target = safeRedirect(redirect)

  async function onPasswordSignIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setMessage(null)
    const form = new FormData(event.currentTarget)
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      credentials: 'include',
      body: new URLSearchParams({
        username: String(form.get('username') ?? ''),
        password: String(form.get('password') ?? ''),
      }),
    })
    setBusy(false)
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      setMessage(
        response.status === 429
          ? 'Too many attempts. Please wait and try again.'
          : typeof body.detail === 'string'
            ? body.detail
            : t('auth.error.generic')
      )
      return
    }
    await queryClient.invalidateQueries({ queryKey: ['session'] })
    navigate({ to: target, replace: true })
  }

  return (
    <AuthLayout>
      <Card className='w-full max-w-sm gap-4'>
        <CardHeader>
          <CardTitle className='text-lg tracking-tight'>
            {t('auth.sign_in')}
          </CardTitle>
        </CardHeader>
        <CardContent className='grid gap-5'>
          {message ? (
            <Alert variant='destructive'>
              <AlertDescription>{message}</AlertDescription>
            </Alert>
          ) : null}

          <div className='grid gap-2'>
            <p className='text-sm font-medium'>{t('auth.staff_title')}</p>
            <CardDescription>{t('auth.staff_hint')}</CardDescription>
            <Button asChild variant='outline' className='gap-2'>
              <a href={microsoftSignInUrl(target)}>
                <MicrosoftLogo />
                {t('auth.microsoft')}
              </a>
            </Button>
          </div>

          <Separator />

          <form className='grid gap-3' onSubmit={onPasswordSignIn}>
            <div>
              <p className='text-sm font-medium'>{t('auth.client_title')}</p>
              <CardDescription>{t('auth.client_hint')}</CardDescription>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='username'>{t('auth.email_or_username')}</Label>
              <Input
                id='username'
                name='username'
                autoComplete='username'
                required
              />
            </div>
            <div className='grid gap-1.5'>
              <div className='flex items-center justify-between'>
                <Label htmlFor='password'>{t('auth.password')}</Label>
                <Link
                  to='/forgot-password'
                  className='text-xs text-muted-foreground hover:underline'
                >
                  {t('auth.forgot')}
                </Link>
              </div>
              <PasswordInput
                id='password'
                name='password'
                autoComplete='current-password'
                required
              />
            </div>
            <Button type='submit' disabled={busy}>
              {busy ? <Loader2 className='animate-spin' /> : null}
              {t('auth.sign_in')}
            </Button>
          </form>
        </CardContent>
      </Card>
    </AuthLayout>
  )
}
