import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { authApi } from '../lib/api'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import LanguageToggle from '../components/ui/LanguageToggle'
import { ArrowRight, KeyRound } from 'lucide-react'

interface FormData {
  email: string
}

export default function ForgotPassword() {
  const { t } = useTranslation()
  const [submitted, setSubmitted] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>()

  const onSubmit = async (data: FormData) => {
    await authApi.forgotPassword(data.email)
    setSubmitted(true)
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
              {t('forgotPassword.heading')}
            </h1>
            <p className="font-mono-label text-muted-foreground">
              {t('forgotPassword.subheading')}
            </p>
          </div>

          {submitted ? (
            <div className="border border-green-700 bg-green-950/20 px-4 py-3">
              <p className="font-mono-label text-green-400">{t('forgotPassword.checkEmail')}</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <Input
                label={t('forgotPassword.emailLabel')}
                type="email"
                placeholder={t('forgotPassword.emailPlaceholder')}
                autoComplete="email"
                {...register('email', {
                  required: t('forgotPassword.emailRequired'),
                  pattern: { value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: t('register.emailInvalid') },
                })}
                error={errors.email?.message}
              />
              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting ? t('forgotPassword.sending') : (
                  <>{t('forgotPassword.sendLink')} <ArrowRight size={14} /></>
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
