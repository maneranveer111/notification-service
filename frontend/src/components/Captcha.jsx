import { useEffect, useRef } from 'react';

export default function Captcha({ siteKey, onToken, resetSignal }) {
  const containerRef = useRef(null);
  const widgetIdRef = useRef(null);

  useEffect(() => {
    if (!siteKey) return;

    function renderWidget() {
      if (!containerRef.current) return;
      widgetIdRef.current = window.turnstile.render(containerRef.current, {
        sitekey: siteKey,
        callback: onToken,
        'error-callback': () => onToken(null),
      });
    }

    if (window.turnstile) {
      renderWidget();
      return;
    }

    let script = document.querySelector('script[src*="turnstile"]');
    if (!script) {
      script = document.createElement('script');
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async = true;
      document.head.appendChild(script);
    }

    let intervalId;
    intervalId = setInterval(() => {
      if (window.turnstile) {
        clearInterval(intervalId);
        renderWidget();
      }
    }, 100);

    return () => clearInterval(intervalId);
  }, [siteKey]);

  useEffect(() => {
    if (widgetIdRef.current != null && window.turnstile) {
      window.turnstile.reset(widgetIdRef.current);
    }
  }, [resetSignal]);

  if (!siteKey) return null;
  return <div ref={containerRef} />;
}
