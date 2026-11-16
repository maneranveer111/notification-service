export function signupState(config) {
  if (!config || typeof config !== 'object') {
    return 'invite_only';
  }
  if (config.needs_setup) {
    return 'setup';
  }
  const mode = config.signup_mode;
  if (mode === 'open' || mode === 'invite_only' || mode === 'closed') {
    return mode;
  }
  return 'invite_only';
}

export function canShowSignupLink(config) {
  const state = signupState(config);
  return state === 'setup' || state === 'open';
}

export function showWorkspaceName(config) {
  return signupState(config) === 'open';
}

export function signupMessage(config) {
  const state = signupState(config);
  if (state === 'invite_only') {
    return 'Signup is by invitation only. Ask a workspace admin to invite you.';
  }
  if (state === 'closed') {
    return 'Signups are disabled';
  }
  return '';
}
