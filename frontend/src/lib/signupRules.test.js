import test from 'node:test';
import assert from 'node:assert/strict';
import {
  signupState,
  canShowSignupLink,
  showWorkspaceName,
  signupMessage,
} from './signupRules.js';

test('needs_setup: true overrides signup_mode=open', () => {
  const cfg = { needs_setup: true, signup_mode: 'open' };
  assert.equal(signupState(cfg), 'setup');
  assert.equal(canShowSignupLink(cfg), true);
  assert.equal(showWorkspaceName(cfg), true);
  assert.equal(signupMessage(cfg), '');
});

test('needs_setup: true overrides signup_mode=invite_only', () => {
  const cfg = { needs_setup: true, signup_mode: 'invite_only' };
  assert.equal(signupState(cfg), 'setup');
  assert.equal(canShowSignupLink(cfg), true);
  assert.equal(showWorkspaceName(cfg), true);
  assert.equal(signupMessage(cfg), '');
});

test('needs_setup: true overrides signup_mode=closed', () => {
  const cfg = { needs_setup: true, signup_mode: 'closed' };
  assert.equal(signupState(cfg), 'setup');
  assert.equal(canShowSignupLink(cfg), true);
  assert.equal(showWorkspaceName(cfg), true);
  assert.equal(signupMessage(cfg), '');
});

test('signup_mode: open with needs_setup: false', () => {
  const cfg = { needs_setup: false, signup_mode: 'open' };
  assert.equal(signupState(cfg), 'open');
  assert.equal(canShowSignupLink(cfg), true);
  assert.equal(showWorkspaceName(cfg), true);
  assert.equal(signupMessage(cfg), '');
});

test('signup_mode: invite_only with needs_setup: false', () => {
  const cfg = { needs_setup: false, signup_mode: 'invite_only' };
  assert.equal(signupState(cfg), 'invite_only');
  assert.equal(canShowSignupLink(cfg), false);
  assert.equal(showWorkspaceName(cfg), false);
  assert.equal(
    signupMessage(cfg),
    'Signup is by invitation only. Ask a workspace admin to invite you.'
  );
});

test('signup_mode: closed with needs_setup: false', () => {
  const cfg = { needs_setup: false, signup_mode: 'closed' };
  assert.equal(signupState(cfg), 'closed');
  assert.equal(canShowSignupLink(cfg), false);
  assert.equal(showWorkspaceName(cfg), false);
  assert.equal(signupMessage(cfg), 'Signups are disabled');
});

test('null config falls back to safest behavior', () => {
  assert.equal(signupState(null), 'invite_only');
  assert.equal(canShowSignupLink(null), false);
  assert.equal(showWorkspaceName(null), false);
  assert.equal(
    signupMessage(null),
    'Signup is by invitation only. Ask a workspace admin to invite you.'
  );
});

test('undefined config falls back to safest behavior', () => {
  assert.equal(signupState(undefined), 'invite_only');
  assert.equal(canShowSignupLink(undefined), false);
  assert.equal(showWorkspaceName(undefined), false);
  assert.equal(
    signupMessage(undefined),
    'Signup is by invitation only. Ask a workspace admin to invite you.'
  );
});

test('empty object falls back to safest behavior', () => {
  assert.equal(signupState({}), 'invite_only');
  assert.equal(canShowSignupLink({}), false);
  assert.equal(showWorkspaceName({}), false);
  assert.equal(
    signupMessage({}),
    'Signup is by invitation only. Ask a workspace admin to invite you.'
  );
});

test('malformed signup_mode falls back to safest behavior', () => {
  const cfg = { signup_mode: 'unknown_garbage', needs_setup: false };
  assert.equal(signupState(cfg), 'invite_only');
  assert.equal(canShowSignupLink(cfg), false);
  assert.equal(showWorkspaceName(cfg), false);
  assert.equal(
    signupMessage(cfg),
    'Signup is by invitation only. Ask a workspace admin to invite you.'
  );
});
