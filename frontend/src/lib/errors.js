export function describeError(err) {
  const code = err?.code;
  const status = err?.status;
  const detail = err?.detail;

  if (code === 'no_provider')
    return {
      title: 'No provider configured',
      message: 'Connect an email or SMS provider to send notifications.',
      action: { label: 'Connect a provider', to: '/settings/providers' },
    };

  if (code === 'provider_not_configured')
    return {
      title: 'Provider not configured',
      message: typeof detail === 'string' ? detail : 'That provider is not configured for this workspace.',
      action: { label: 'Configure providers', to: '/settings/providers' },
    };

  if (code === 'quota_exceeded')
    return {
      title: 'Quota exceeded',
      message: typeof detail === 'string' ? detail : 'You have exceeded your notification quota.',
    };

  if (code === 'plan_limit')
    return {
      title: 'Plan limit reached',
      message: typeof detail === 'string' ? detail : 'Your plan limit has been reached.',
    };

  if (code === 'email_not_verified')
    return {
      title: 'Email not verified',
      message: 'Please verify your email address before logging in.',
    };

  if (code === 'captcha_failed')
    return {
      title: 'CAPTCHA failed',
      message: 'The CAPTCHA check failed. Please try again.',
    };

  if (code === 'captcha_unavailable' || status === 503)
    return {
      title: 'Service unavailable',
      message: 'The service is temporarily unavailable. Please try again later.',
    };

  if (status === 429)
    return {
      title: 'Too many requests',
      message: "You've made too many requests. Please wait a moment and try again.",
    };

  if (status === 403)
    return {
      title: 'Access denied',
      message: typeof detail === 'string' ? detail : "You don't have permission to do this.",
    };

  if (status === 404)
    return {
      title: 'Not found',
      message: typeof detail === 'string' ? detail : 'The requested resource was not found.',
    };

  if (status === 422 && Array.isArray(detail))
    return {
      title: 'Validation error',
      message: detail
        .map(d => (d.loc ? `${d.loc[d.loc.length - 1]}: ${d.msg}` : d.msg))
        .join('; '),
    };

  if (!status)
    return {
      title: 'Network error',
      message: 'Could not reach the server. Check your connection.',
    };

  return {
    title: 'Something went wrong',
    message: err?.message || 'An unexpected error occurred.',
  };
}
