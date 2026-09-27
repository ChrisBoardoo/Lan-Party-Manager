import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { authApi } from '../lib/api'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import LanguageToggle from '../components/ui/LanguageToggle'
import { ArrowRight, KeyRound } from 'lucide-react'

interface FormData {
  new_password: string
  confirm_new_password: string
}

export default function ResetPassword() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''
  const [error, setError] = useState('')
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormData>()

  const onSubmit = async (data: FormData) => {
    setError('')
    try {
      await authApi.resetPassword(token, data.new_password)
      navigate('/login', { state: { passwordReset: true } })
    } catch (e: any) {
      setError(e.response?.data?.detail ?? t('resetPassword.resetFailed'))
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <div className="flex justify-end px-6 pt-4">
        <LanguageToggle />
      </div>
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="max-w-sm w-full">
          <div className="mb-8">
            <KeyRound size={18} strokeWidth={1.5} className="text-accent mb-4" />
            <h1 className="text-3xl font-black tracking-tight text-foreground mb-1">
              {t('resetPassword.heading')}
            </h1>
            <p className="font-mono-label text-muted-foreground">
              {t('resetPassword.subheading')}
            </p>
          </div>

          {!token ? (
            <div className="border border-red-800 bg-red-950/20 px-4 py-3">
              <p className="font-mono-label text-red-400">{t('resetPassword.missingToken')}</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <Input
                label={t('resetPassword.newPasswordLabel')}
                type="password"
                autoComplete="new-password"
                {...register('new_password', {
                  required: t('resetPassword.newPasswordRequired'),
                  minLength: { value: 6, message: t('register.passwordMinLength') },
                  validate: (v) =>
                    new TextEncoder().encode(v).length <= 72 || t('register.passwordMaxLength'),
                })}
                error={errors.new_password?.message}
              />
              <Input
                label={t('resetPassword.confirmNewPasswordLabel')}
                type="password"
                autoComplete="new-password"
                {...register('confirm_new_password', {
                  required: t('resetPassword.confirmNewPasswordRequired'),
                  validate: (v) => v === watch('new_password') || t('register.passwordsNoMatch'),
                })}
                error={errors.confirm_new_password?.message}
              />

              {error && (
                <div className="border border-red-800 bg-red-950/20 px-4 py-3">
                  <p className="font-mono-label text-red-400">{error}</p>
                </div>
              )}

              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? t('resetPassword.resetting') : (
                  <>{t('resetPassword.resetButton')} <ArrowRight size={14} /></>
                )}
              </Button>
            </form>
          )}

          <div className="mt-8 pt-6 border-t border-border">
            <p className="font-mono-label text-muted-foreground">
              <Link to="/login" className="text-accent hover:text-accent/80 transition-colors">
                {t('forgotPassword.backToLogin')} →
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
