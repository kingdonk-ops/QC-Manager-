import { useState } from 'react'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { api } from '@/api/client'
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
import { PasswordInput } from '@/components/password-input'
import { AuthLayout } from '../auth-layout'

/** Asks for a reset link. Answers the same whether or not the address has an account. */
export function ForgotPassword() {
  const [sent, setSent] = useState(false)

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const email = String(new FormData(event.currentTarget).get('email') ?? '')
    await api.POST('/api/v1/auth/password/reset-request', {
      body: { email } as never,
    })
    setSent(true)
  }

  return (
    <AuthLayout>
      <Card className='w-full max-w-sm gap-4'>
        <CardHeader>
          <CardTitle className='text-lg'>Reset your password</CardTitle>
          <CardDescription>
            For client and partner accounts. Staff reset their password with
            Microsoft.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {sent ? (
            <Alert>
              <AlertDescription>
                If an account exists for that address, we've emailed a link to
                set a new password.
              </AlertDescription>
            </Alert>
          ) : (
            <form className='grid gap-3' onSubmit={onSubmit}>
              <div className='grid gap-1.5'>
                <Label htmlFor='email'>Email</Label>
                <Input
                  id='email'
                  name='email'
                  type='email'
                  autoComplete='email'
                  required
                />
              </div>
              <Button type='submit'>Send link</Button>
            </form>
          )}
          <p className='mt-4 text-center text-sm'>
            <Link to='/sign-in' className='underline underline-offset-4'>
              Back to sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </AuthLayout>
  )
}

/** Where invitation and reset emails land: sets the password from the token in the link. */
export function ResetPassword() {
  const { token } = useSearch({ from: '/(auth)/reset-password' })
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const password = String(form.get('password') ?? '')
    if (password !== String(form.get('confirm') ?? '')) {
      setError('The passwords do not match.')
      return
    }
    const { response, error: body } = await api.POST(
      '/api/v1/auth/password/reset-confirm',
      {
        body: { token: token ?? '', new_password: password } as never,
      }
    )
    if (!response.ok) {
      const detail = (body as { detail?: unknown } | undefined)?.detail
      setError(
        typeof detail === 'string'
          ? detail
          : 'That link has expired or the password does not meet the policy.'
      )
      return
    }
    navigate({ to: '/sign-in', replace: true })
  }

  return (
    <AuthLayout>
      <Card className='w-full max-w-sm gap-4'>
        <CardHeader>
          <CardTitle className='text-lg'>Set your password</CardTitle>
          <CardDescription>
            At least 8 characters, with upper and lower case, a digit and a
            symbol.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <Alert variant='destructive' className='mb-3'>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <form className='grid gap-3' onSubmit={onSubmit}>
            <div className='grid gap-1.5'>
              <Label htmlFor='password'>New password</Label>
              <PasswordInput
                id='password'
                name='password'
                autoComplete='new-password'
                required
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='confirm'>Confirm password</Label>
              <PasswordInput
                id='confirm'
                name='confirm'
                autoComplete='new-password'
                required
              />
            </div>
            <Button type='submit' disabled={!token}>
              Set password
            </Button>
          </form>
        </CardContent>
      </Card>
    </AuthLayout>
  )
}
